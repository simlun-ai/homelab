"""Administration boundaries with public fixtures and no native or hardware calls."""

import importlib.util
import io
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/trust_talos_admin.py"
spec = importlib.util.spec_from_file_location("trust_talos_admin", SCRIPT)
assert spec is not None and spec.loader is not None
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class AdminTests(unittest.TestCase):
    def test_node_address_comes_from_committed_patch(self) -> None:
        self.assertEqual(module.node_address(), "10.10.0.10")

    def test_missing_record_never_queries_token_or_generates_identity(self) -> None:
        with TemporaryDirectory() as directory:
            with (
                patch.object(module.secrets, "require_private_repository"),
                patch.object(module.secrets, "recover_bundle") as recover,
                patch.object(module.secrets, "generate") as generate,
            ):
                with self.assertRaises(module.secrets.PreflightError):
                    module.inspect(
                        "/talosctl",
                        "/unwrap",
                        Path("/ram"),
                        record=Path(directory) / "missing",
                    )
                recover.assert_not_called()
                generate.assert_not_called()

    def test_only_public_metadata_is_printed(self) -> None:
        with TemporaryDirectory() as directory:
            record = Path(directory) / "record"
            record.write_bytes(b"PUBLIC ciphertext fixture")
            info = {
                "context": "trust",
                "endpoints": ["10.10.0.10"],
                "nodes": ["10.10.0.10"],
                "roles": ["os:admin"],
                "key": "DO NOT PRINT",
                "certNotAfter": "2026-11-09",
            }
            output = io.StringIO()
            with (
                patch.object(module.secrets, "require_private_repository"),
                patch.object(module.credentials, "ram_directory"),
                patch.object(
                    module.secrets, "recover_bundle", return_value=b"PUBLIC bundle"
                ),
                patch.object(
                    module.recovery,
                    "talos_ca",
                    return_value=(b"PUBLIC CA", b"PUBLIC key"),
                ),
                patch.object(
                    module.credentials, "issue", return_value=b"PUBLIC client"
                ) as issue,
                patch.object(module.config, "validate_client", return_value=info),
                redirect_stdout(output),
            ):
                result = module.inspect(
                    "/talosctl", "/unwrap", Path("/ram"), record=record
                )
            self.assertNotIn("key", result)
            self.assertNotIn("DO NOT PRINT", output.getvalue())
            self.assertEqual(
                issue.call_args.kwargs, {"context": "trust", "node": "10.10.0.10"}
            )

    def test_ambiguous_node_address_fails(self) -> None:
        with patch.object(module.yaml, "safe_load_all", return_value=[]):
            with self.assertRaises(ValueError):
                module.node_address()


if __name__ == "__main__":
    unittest.main()
