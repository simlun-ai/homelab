"""Test Trust OpenTofu chart downloads and secret handling."""

import hashlib
import json
import unittest
from contextlib import nullcontext, redirect_stdout
from io import BytesIO, StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import trust_tofu


class TrustTofuTests(unittest.TestCase):
    def test_oci_chart_verifies_manifest_and_layer(self) -> None:
        repository = "oci://registry.example/charts/test"
        archive = b"valid chart bytes"
        digest = f"sha256:{hashlib.sha256(archive).hexdigest()}"
        manifest = json.dumps(
            {
                "schemaVersion": 2,
                "config": {"mediaType": trust_tofu.HELM_CONFIG},
                "layers": [
                    {"mediaType": "application/vnd.cncf.helm.chart.provenance.v1.prov"},
                    {
                        "mediaType": trust_tofu.HELM_CHART,
                        "digest": digest,
                        "size": len(archive),
                    },
                ],
            }
        ).encode()
        manifest_digest = f"sha256:{hashlib.sha256(manifest).hexdigest()}"
        with patch(
            "trust_tofu.urllib.request.urlopen",
            side_effect=(BytesIO(manifest), BytesIO(archive)),
        ) as fetch:
            self.assertEqual(
                trust_tofu.fetch_oci_chart(repository, manifest_digest), archive
            )
            self.assertEqual(
                fetch.call_args_list[0].args[0].full_url,
                f"https://registry.example/v2/charts/test/manifests/{manifest_digest}",
            )
            self.assertEqual(
                fetch.call_args_list[1].args[0],
                f"https://registry.example/v2/charts/test/blobs/{digest}",
            )

        with patch(
            "trust_tofu.urllib.request.urlopen", return_value=BytesIO(manifest + b" ")
        ) as fetch:
            with self.assertRaisesRegex(ValueError, "manifest digest mismatch"):
                trust_tofu.fetch_oci_chart(repository, manifest_digest)
            fetch.assert_called_once()

        with patch(
            "trust_tofu.urllib.request.urlopen",
            side_effect=(BytesIO(manifest), BytesIO(b"wrong chart bytes")),
        ):
            with self.assertRaisesRegex(ValueError, "content digest or size mismatch"):
                trust_tofu.fetch_oci_chart(repository, manifest_digest)

    def test_key_session_reuses_one_recovery_for_multiple_provider_requests(
        self,
    ) -> None:
        key = bytes(range(32))
        scope = trust_tofu.tofu_key.StateScope.INFRASTRUCTURE
        with (
            TemporaryDirectory() as directory,
            patch.object(
                trust_tofu.recovery.secrets,
                "executable",
                return_value="/disposable/homelab-unwrap",
            ),
            patch.object(trust_tofu.tofu_key, "recover", return_value=key) as recover,
        ):
            address = Path(directory) / "key.sock"
            try:
                with trust_tofu.key_session(address, scope):
                    for _ in range(4):
                        self.assertEqual(
                            trust_tofu.tofu_key.read_session_key(address), key
                        )
            except PermissionError:
                if address.exists():
                    raise
                self.skipTest("This environment forbids local Unix sockets")
            recover.assert_called_once_with("/disposable/homelab-unwrap", scope)
            with self.assertRaises(ConnectionRefusedError):
                trust_tofu.tofu_key.read_session_key(address)

    def test_workload_key_provider_rejects_infrastructure_state_metadata(self) -> None:
        key_provider = trust_tofu.tofu_key
        infrastructure_metadata = {
            "external_data": {
                "key_id": "homelab/v1/trust/opentofu/state/infrastructure/r1"
            }
        }
        workload_metadata = {
            "external_data": {"key_id": "homelab/v1/trust/opentofu/state/workload/r1"}
        }
        address = Path("/disposable/key.sock")
        scope = key_provider.StateScope.WORKLOAD

        with (
            patch.object(key_provider.secrets, "require_pipe"),
            patch.object(
                key_provider, "read_session_key", return_value=bytes(32)
            ) as read,
            patch("sys.stdin", StringIO(json.dumps(infrastructure_metadata))),
            redirect_stdout(StringIO()),
        ):
            with self.assertRaisesRegex(
                ValueError, "Unexpected OpenTofu state key metadata"
            ):
                key_provider.provide(address, scope)
            read.assert_not_called()

        with (
            patch.object(key_provider.secrets, "require_pipe"),
            patch.object(
                key_provider, "read_session_key", return_value=bytes(32)
            ) as read,
            patch("sys.stdin", StringIO(json.dumps(workload_metadata))),
            redirect_stdout(StringIO()) as output,
        ):
            key_provider.provide(address, scope)
            read.assert_called_once_with(address)
        response = json.loads(output.getvalue().splitlines()[1])
        self.assertEqual(response["meta"], workload_metadata)
        self.assertEqual(
            response["keys"]["encryption_key"], response["keys"]["decryption_key"]
        )

    def test_cert_manager_token_recovery_uses_dedicated_record(self) -> None:
        with (
            patch.object(
                trust_tofu.recovery.secrets,
                "executable",
                return_value="/disposable/homelab-unwrap",
            ),
            patch.object(
                trust_tofu.recovery.secrets,
                "hsm_progress_terminal",
                return_value=nullcontext(2),
            ),
            patch.object(
                trust_tofu.recovery.secrets,
                "recover_bundle",
                side_effect=(b"disposable-token", b"malformed\nrecord"),
            ) as recover,
        ):
            self.assertEqual(trust_tofu.recover_cloudflare_token(), "disposable-token")
            recover.assert_called_once_with(
                "/disposable/homelab-unwrap",
                record=trust_tofu.ROOT
                / "secrets/wrapped/trust-cert-manager-cloudflare.json",
                key_id="homelab/v1/trust/cert-manager/dns-api/cloudflare/r1",
                stderr=2,
            )
            with self.assertRaises(trust_tofu.recovery.secrets.PreflightError):
                trust_tofu.recover_cloudflare_token()
