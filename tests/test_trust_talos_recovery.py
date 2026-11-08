"""Recovery boundaries with public fixtures; no token or native signing calls."""

import base64
import contextlib
import importlib.util
import io
import unittest
from pathlib import Path
from unittest.mock import patch

import yaml

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/trust_talos_recovery.py"
spec = importlib.util.spec_from_file_location("trust_talos_recovery", SCRIPT)
assert spec is not None and spec.loader is not None
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def encoded(value: bytes) -> str:
    return base64.b64encode(value).decode("ascii")


def client(ca: bytes, crt: bytes, key: bytes) -> bytes:
    return yaml.safe_dump(
        {
            "contexts": {
                module.config.CLUSTER: {
                    "ca": encoded(ca),
                    "crt": encoded(crt),
                    "key": encoded(key),
                }
            }
        }
    ).encode()


class RecoveryTests(unittest.TestCase):
    def test_existing_os_ca_is_required(self) -> None:
        bundle = yaml.safe_dump(
            {
                "certs": {
                    "os": {"crt": encoded(b"PUBLIC CA"), "key": encoded(b"PUBLIC key")}
                }
            }
        ).encode()
        self.assertEqual(module.talos_ca(bundle), (b"PUBLIC CA", b"PUBLIC key"))
        for invalid in (b"{}", b"certs: {os: {crt: '***', key: eA==}}", b"[]"):
            with (
                self.subTest(bundle=invalid),
                self.assertRaises((ValueError, KeyError)),
            ):
                module.talos_ca(invalid)

    def test_missing_ca_never_invokes_native_generation(self) -> None:
        with patch.object(module.config, "generate") as generate:
            with self.assertRaises(KeyError):
                module.prepare("/talosctl", b"{}", Path("/ram"))
            generate.assert_not_called()

    def test_machine_authority_mismatch_prevents_issuance(self) -> None:
        machine = yaml.safe_dump(
            {"version": "v1alpha1", "machine": {"ca": {"crt": encoded(b"other")}}}
        ).encode()
        with (
            patch.object(module, "talos_ca", return_value=(b"CA", b"key")),
            patch.object(module.config, "generate", return_value=machine),
            patch.object(module.config, "validate_machine"),
            patch.object(module.credentials, "issue") as issue,
        ):
            with self.assertRaises(ValueError):
                module.prepare("/talosctl", b"bundle", Path("/ram"))
            issue.assert_not_called()

    def test_reissuance_requires_same_bundle_and_fresh_material(self) -> None:
        first = client(b"CA", b"crt1", b"key1")
        second = client(b"CA", b"crt2", b"key2")
        cases = (
            ([b"bundle", b"bundle"], [first, second], False),
            ([b"bundle", b"changed"], [first, second], True),
            ([b"bundle", b"bundle"], [first, client(b"other", b"crt2", b"key2")], True),
            ([b"bundle", b"bundle"], [first, client(b"CA", b"crt1", b"key2")], True),
            ([b"bundle", b"bundle"], [first, client(b"CA", b"crt2", b"key1")], True),
        )
        for bundles, clients, fails in cases:
            with (
                self.subTest(bundles=bundles, fails=fails),
                patch.object(module, "prepare", side_effect=clients),
                contextlib.redirect_stdout(io.StringIO()),
            ):
                recovered = iter(bundles)
                if fails:
                    with self.assertRaises(ValueError):
                        module.exercise("/talosctl", Path("/ram"), recovered.__next__)
                else:
                    module.exercise("/talosctl", Path("/ram"), recovered.__next__)

    def test_failed_recovery_does_not_generate_replacement(self) -> None:
        def failed() -> bytes:
            raise RuntimeError("PUBLIC fixture failure")

        with patch.object(module, "prepare") as prepare:
            with self.assertRaises(RuntimeError):
                module.exercise("/talosctl", Path("/ram"), failed)
            prepare.assert_not_called()


if __name__ == "__main__":
    unittest.main()
