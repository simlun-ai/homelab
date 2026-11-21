"""Protect the staged OpenBao credential transport from regressions."""

import json
import unittest
from unittest.mock import patch

import trust_openbao


class TrustOpenBaoTests(unittest.TestCase):
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
