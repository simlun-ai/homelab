"""Safe unit tests: Talos and HSM subprocesses are mocked, no keys created."""

import importlib.util
import unittest
from pathlib import Path
from unittest.mock import patch

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/trust_talos_secrets.py"
spec = importlib.util.spec_from_file_location("trust_talos_secrets", SCRIPT)
assert spec is not None and spec.loader is not None
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class TrustSecretsTests(unittest.TestCase):
    def test_version_mismatch_rejected(self) -> None:
        with patch.object(module.subprocess, "run") as run:
            run.return_value.stdout = b"v1.14.4"
            with self.assertRaises(ValueError):
                module.check_version("/abs/talosctl")

    def test_generation_uses_stdout_not_file(self) -> None:
        with patch.object(module.subprocess, "run") as run:
            run.return_value.stdout = b"fake disposable bundle"
            self.assertEqual(
                module.generate("/abs/talosctl"), b"fake disposable bundle"
            )
            argv = run.call_args.args[0]
            self.assertEqual(argv[-2:], ["--output-file", "-"])

    def test_init_refuses_existing_record_before_tool_calls(self) -> None:
        with patch.object(module.os.path, "lexists", return_value=True):
            with patch.object(module, "generate") as generate:
                with self.assertRaises(FileExistsError):
                    module.initialize("/abs/talosctl", "/abs/homelab-wrap")
                generate.assert_not_called()

    def test_init_only_passes_plaintext_over_stdin(self) -> None:
        with (
            patch.object(module.os.path, "lexists", return_value=False),
            patch.object(module, "check_version"),
            patch.object(module, "generate", return_value=b"disposable"),
            patch.object(module.subprocess, "run") as run,
        ):
            module.initialize("/abs/talosctl", "/abs/homelab-wrap")
            self.assertEqual(run.call_args.kwargs["input"], b"disposable")
            self.assertIn("--stdin", run.call_args.args[0])
            self.assertNotIn("disposable", " ".join(run.call_args.args[0]))

    def test_recover_refuses_non_pipe(self) -> None:
        with patch.object(module, "require_pipe", side_effect=ValueError):
            with patch.object(module.subprocess, "Popen") as popen:
                with self.assertRaises(ValueError):
                    module.recover("/abs/homelab-unwrap")
                popen.assert_not_called()

    def test_record_does_not_contain_private_keys(self) -> None:
        self.assertEqual(module.KEY_ID, "homelab/v1/trust/talos/bootstrap/r1")
        self.assertTrue(module.RECORD.name.endswith(".json"))


if __name__ == "__main__":
    unittest.main()
