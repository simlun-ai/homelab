"""Disposable subprocess/Git tests; Talos and HSM operations are mocked."""

import importlib.util
import io
import subprocess
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import Mock, patch

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/trust_talos_secrets.py"
spec = importlib.util.spec_from_file_location("trust_talos_secrets", SCRIPT)
assert spec is not None and spec.loader is not None
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class TrustSecretsTests(unittest.TestCase):
    def test_reads_version_from_cluster_scope(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            versions = root / "clusters/trust/versions.yaml"
            versions.parent.mkdir(parents=True)
            versions.write_text("talos:\n  version: v2.3.4\n", encoding="utf-8")
            with patch.object(module, "ROOT", root):
                self.assertEqual(module.talos_version(), "v2.3.4")

    def test_generation_uses_stdout_not_file(self) -> None:
        with patch.object(module, "capture_bundle") as run:
            run.return_value = b"fake disposable bundle"
            self.assertEqual(
                module.generate("/abs/talosctl"), b"fake disposable bundle"
            )
            argv = run.call_args.args[0]
            self.assertEqual(argv[-2:], ["--output-file", "-"])
            self.assertEqual(
                argv[argv.index("--talos-version") + 1], module.talos_version()
            )

    def test_init_refuses_existing_record_before_tool_calls(self) -> None:
        with patch.object(module.os.path, "lexists", return_value=True):
            with patch.object(module, "generate") as generate:
                with self.assertRaises(FileExistsError):
                    module.initialize("/abs/talosctl", "/abs/homelab-wrap")
                generate.assert_not_called()

    def test_init_only_passes_plaintext_over_stdin(self) -> None:
        with (
            patch.object(module.os.path, "lexists", return_value=False),
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

    def test_capture_rejects_empty_failed_and_oversized_children(self) -> None:
        cases = [
            ("pass", ValueError),
            ("import sys; print('disposable'); sys.exit(1)", RuntimeError),
            ("print('x' * 4096)", ValueError),
        ]
        for code, error in cases:
            with self.subTest(code=code), patch.object(module, "MAX_SECRETS", 1024):
                with self.assertRaises(error):
                    module.capture_bundle([sys.executable, "-c", code], timeout=5)

    def test_capture_times_out_while_child_keeps_stdout_open(self) -> None:
        with self.assertRaises(TimeoutError):
            module.capture_bundle(
                [sys.executable, "-c", "import time; time.sleep(10)"], timeout=0.1
            )

    def test_capture_times_out_after_stdout_closes(self) -> None:
        with self.assertRaises(subprocess.TimeoutExpired):
            module.capture_bundle(
                [sys.executable, "-c", "import os,time; os.close(1); time.sleep(10)"],
                timeout=0.1,
            )

    def test_capture_success(self) -> None:
        self.assertEqual(
            module.capture_bundle(
                [sys.executable, "-c", "print('disposable')"], timeout=5
            ),
            b"disposable\n",
        )

    def test_recover_emits_nothing_on_child_failure(self) -> None:
        with TemporaryDirectory() as directory:
            record = Path(directory) / "record.json"
            record.write_text("{}")
            output = Mock(buffer=io.BytesIO())
            with (
                patch.object(module, "RECORD", record),
                patch.object(module, "require_pipe"),
                patch.object(module.sys, "stdout", output),
                patch.object(module, "capture_bundle", side_effect=RuntimeError),
            ):
                with self.assertRaises(RuntimeError):
                    module.recover("/abs/homelab-unwrap")
            self.assertEqual(output.buffer.getvalue(), b"")

    def test_private_repository_requires_initialized_gitlink(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory) / "parent"
            root.mkdir()
            wrapped = root / "secrets/wrapped"
            wrapped.mkdir(parents=True)
            subprocess.run(["git", "init", "-q", str(root)], check=True)
            with (
                patch.object(module, "ROOT", root),
                patch.object(module, "RECORD", wrapped / "record.json"),
            ):
                # An ordinary directory must fail, even inside a Git checkout.
                with self.assertRaises(ValueError):
                    module.require_private_repository()
                subprocess.run(
                    [
                        "git",
                        "-C",
                        str(root),
                        "update-index",
                        "--add",
                        "--cacheinfo",
                        "160000," + "1" * 40 + ",secrets/wrapped",
                    ],
                    check=True,
                )
                # An uninitialized submodule resolves to its parent repository.
                with self.assertRaises(ValueError):
                    module.require_private_repository()
                subprocess.run(["git", "init", "-q", str(wrapped)], check=True)
                module.require_private_repository()
                wrapped.rename(root / "records")
                wrapped.symlink_to(root / "records", target_is_directory=True)
                with self.assertRaises(ValueError):
                    module.require_private_repository()

    def test_record_does_not_contain_private_keys(self) -> None:
        self.assertEqual(module.KEY_ID, "homelab/v1/trust/talos/bootstrap/r1")
        self.assertTrue(module.RECORD.name.endswith(".json"))


if __name__ == "__main__":
    unittest.main()
