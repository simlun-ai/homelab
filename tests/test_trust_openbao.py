"""Protect the staged OpenBao credential transport from regressions."""

import json
import sys
import unittest
from contextlib import nullcontext
from subprocess import CompletedProcess
from unittest.mock import patch

import trust_openbao


class TrustOpenBaoTests(unittest.TestCase):
    def test_restart_is_a_cli_action(self) -> None:
        with (
            patch.object(sys, "argv", ["trust_openbao.py", "restart"]),
            patch.object(trust_openbao.secrets, "harden"),
            patch.object(trust_openbao.secrets, "executable", return_value="kubectl"),
            patch.object(trust_openbao.os, "umask"),
            patch.object(trust_openbao.tofu, "get_kubeconfig", return_value=b"config"),
            patch.object(
                trust_openbao.tofu.recovery.config,
                "memory_file",
                return_value=nullcontext(7),
            ),
            patch.object(trust_openbao, "restart") as restart,
        ):
            self.assertEqual(trust_openbao.main(), 0)
        restart.assert_called_once_with(
            ["kubectl", "--kubeconfig", "/proc/self/fd/7"], 7
        )

    def test_status_passes_only_status_arguments_to_bao(self) -> None:
        output = b'{"type":"shamir","initialized":true,"sealed":false}'
        with patch.object(
            trust_openbao.subprocess,
            "run",
            return_value=CompletedProcess(["kubectl"], 0, output),
        ) as run:
            self.assertEqual(trust_openbao.status(["kubectl"], 7, ()), (True, False))
        self.assertEqual(
            run.call_args.args[0],
            ["kubectl", "--", "bao", "status", "-format=json", "-non-interactive"],
        )

    def test_restart_waits_for_replacement_container_without_readiness(self) -> None:
        annotations = {"openbao.hashicorp.com/config-checksum": "checksum"}
        statefulset = {
            "metadata": {"generation": 2},
            "status": {"observedGeneration": 2, "updateRevision": "revision"},
            "spec": {"template": {"metadata": {"annotations": annotations}}},
        }
        metadata = {
            "uid": "old",
            "labels": {"controller-revision-hash": "revision"},
            "annotations": annotations,
        }
        running: dict[str, str] = {}
        pod = {
            "metadata": metadata,
            "status": {
                "containerStatuses": [
                    {"name": "openbao", "ready": False, "state": {"running": running}}
                ]
            },
        }
        old = json.dumps(pod).encode()
        metadata["uid"] = "replacement"
        responses: list[CompletedProcess[bytes]] = [
            CompletedProcess(["kubectl"], 0, json.dumps(statefulset).encode()),
            CompletedProcess(["kubectl"], 0, old),
            CompletedProcess(["kubectl"], 0, b""),
            CompletedProcess(["kubectl"], 0, old),
            CompletedProcess(["kubectl"], 0, json.dumps(pod).encode()),
        ]
        with (
            patch.object(trust_openbao.subprocess, "run", side_effect=responses) as run,
            patch.object(trust_openbao.time, "sleep"),
        ):
            trust_openbao.restart(["kubectl"], 7)

        delete = run.call_args_list[2]
        self.assertEqual(
            delete.args[0],
            [
                "kubectl",
                "delete",
                "--raw",
                "/api/v1/namespaces/openbao/pods/openbao-0",
                "-f",
                "-",
            ],
        )
        self.assertEqual(
            json.loads(delete.kwargs["input"])["preconditions"], {"uid": "old"}
        )
        self.assertEqual(run.call_count, 5)

    def test_parse_valid_single_share(self) -> None:
        response = json.dumps(
            {
                "unseal_keys_b64": ["YQ=="],
                "unseal_shares": 1,
                "unseal_threshold": 1,
                "root_token": "disposable-token",
            }
        ).encode()
        self.assertEqual(
            trust_openbao.parse_initialization(response),
            (b"YQ==", b"disposable-token"),
        )
        with self.assertRaises(ValueError):
            trust_openbao.parse_initialization(response.replace(b'"YQ=="', b'"!"'))

    def test_unseal_share_uses_json_stdin(self) -> None:
        with (
            patch.object(
                trust_openbao, "status", side_effect=((True, True), (True, False))
            ),
            patch.object(trust_openbao.secrets, "recover_bundle", return_value=b"YQ=="),
            patch.object(trust_openbao.subprocess, "run") as run,
        ):
            trust_openbao.unseal(["kubectl", "exec"], 7, "/bin/homelab-unwrap", 8)
        args = run.call_args.args[0]
        self.assertEqual(args[:6], ["kubectl", "exec", "-i", "--", "bao", "write"])
        self.assertEqual(args[-2:], ["sys/unseal", "-"])
        self.assertIn("-tls-skip-verify=false", args)
        self.assertNotIn("-non-interactive", args)
        self.assertNotIn("YQ==", args)
        self.assertEqual(json.loads(run.call_args.kwargs["input"]), {"key": "YQ=="})

    def test_refuse_initialization_when_either_record_exists(self) -> None:
        with (
            patch.object(trust_openbao.os.path, "lexists", return_value=True),
            patch.object(trust_openbao, "status") as status,
        ):
            with self.assertRaisesRegex(ValueError, "already exists"):
                trust_openbao.initialize(["kubectl", "exec"], 7, "wrap", "unwrap", 8)
            status.assert_not_called()
