"""Disposable subprocess/Git tests; Talos and HSM operations are mocked."""

import importlib.util
import io
import json
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

    def test_swap_check_reports_a_public_preflight_error(self) -> None:
        with (
            patch.object(module.resource, "setrlimit"),
            patch.object(module.logging, "disable"),
            patch.object(module.ctypes, "CDLL") as libc,
            patch.object(Path, "read_text", return_value="Filename\n/dev/zram0\n"),
        ):
            libc.return_value.prctl.return_value = 0
            with self.assertRaisesRegex(module.PreflightError, "Swap is enabled"):
                module.harden()

    def test_main_reports_missing_executable_without_starting_rehearsal(self) -> None:
        output = io.StringIO()
        with (
            patch.object(module, "harden"),
            patch.object(
                module.sys,
                "argv",
                [
                    "trust_talos_secrets.py",
                    "rehearse",
                    "--talosctl",
                    "/definitely-missing/talosctl",
                    "--wrap",
                    "/definitely-missing/wrap",
                    "--unwrap",
                    "/definitely-missing/unwrap",
                ],
            ),
            patch.object(module.sys, "stderr", output),
            patch.object(module, "rehearse") as rehearse,
        ):
            self.assertEqual(module.main(), 1)
            rehearse.assert_not_called()
        self.assertIn("talosctl: an existing absolute executable", output.getvalue())

    def test_main_reports_stage_without_exception_details(self) -> None:
        output = io.StringIO()
        with (
            patch.object(module, "harden"),
            patch.object(module, "executable", return_value="/abs/tool"),
            patch.object(
                module, "rehearse", side_effect=RuntimeError("sensitive-marker")
            ),
            patch.object(
                module.sys,
                "argv",
                [
                    "trust_talos_secrets.py",
                    "rehearse",
                    "--talosctl",
                    "/abs/tool",
                    "--wrap",
                    "/abs/tool",
                    "--unwrap",
                    "/abs/tool",
                ],
            ),
            patch.object(module.sys, "stderr", output),
        ):
            self.assertEqual(module.main(), 1)
        self.assertIn("during rehearsal", output.getvalue())
        self.assertNotIn("sensitive-marker", output.getvalue())

    def test_rehearsal_is_isolated_and_prints_no_bundle(self) -> None:
        plaintext = b"disposable-test-bundle-do-not-print"
        encoded = b'{"ciphertext": "AQID"}'
        created: list[Path] = []

        def wrap_bundle(data: bytes, _cli: str, *, record: Path, key_id: str) -> None:
            self.assertEqual(data, plaintext)
            self.assertEqual(key_id, "homelab/v1/trust/talos/rehearsal/r1")
            self.assertNotEqual(record, module.RECORD)
            if record.exists():
                raise FileExistsError
            record.write_bytes(encoded)
            created.append(record)

        def recover_bundle(_cli: str, *, record: Path, key_id: str) -> bytes:
            self.assertEqual(key_id, "homelab/v1/trust/talos/rehearsal/r1")
            data = record.read_bytes()
            if data != encoded:
                # The corruption fixture remains parseable JSON/Base64.
                self.assertIsInstance(json.loads(data)["ciphertext"], str)
                raise RuntimeError
            return plaintext

        output = io.StringIO()
        with (
            patch.object(module, "generate", return_value=plaintext),
            patch.object(module, "wrap_bundle", side_effect=wrap_bundle) as wrap,
            patch.object(
                module, "recover_bundle", side_effect=recover_bundle
            ) as unwrap,
            patch.object(module.sys, "stdout", output),
        ):
            module.rehearse("/abs/talosctl", "/abs/wrap", "/abs/unwrap")
        self.assertEqual(wrap.call_count, 2)
        self.assertEqual(unwrap.call_count, 3)
        self.assertNotIn(plaintext.decode(), output.getvalue())
        self.assertIn("PASS: rehearsal complete", output.getvalue())
        self.assertEqual(len(created), 1)
        self.assertFalse(created[0].parents[2].exists())

    def test_rehearsal_mismatch_fails_and_cleans_up(self) -> None:
        records: list[Path] = []

        def wrap_bundle(_data: bytes, _cli: str, *, record: Path, key_id: str) -> None:
            self.assertIn("rehearsal", key_id)
            record.write_bytes(b"ciphertext-only")
            records.append(record)

        with (
            patch.object(module, "generate", return_value=b"disposable"),
            patch.object(module, "wrap_bundle", side_effect=wrap_bundle),
            patch.object(module, "recover_bundle", return_value=b"mismatch"),
            patch.object(module.sys, "stdout", io.StringIO()),
        ):
            with self.assertRaisesRegex(ValueError, "did not match"):
                module.rehearse("/abs/talosctl", "/abs/wrap", "/abs/unwrap")
        self.assertFalse(records[0].parents[2].exists())


if __name__ == "__main__":
    unittest.main()
