"""Protected descriptor tests with disposable bytes, never real credentials."""

import errno
import importlib.util
import json
import os
import subprocess
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/trust_talos_config.py"
spec = importlib.util.spec_from_file_location("trust_talos_config", SCRIPT)
assert spec is not None and spec.loader is not None
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class TalosConfigTests(unittest.TestCase):
    def test_child_reads_only_explicitly_inherited_descriptor(self) -> None:
        with module.memory_file(b"disposable") as fd:
            result = module.secrets.capture_bundle(
                [
                    sys.executable,
                    "-I",
                    "-B",
                    "-c",
                    "import os,sys; sys.stdout.buffer.write(os.read(int(sys.argv[1]), 100))",
                    str(fd),
                ],
                timeout=5,
                pass_fds=(fd,),
            )
        self.assertEqual(result, b"disposable")

    def test_descriptor_is_private_immutable_and_closed(self) -> None:
        with module.memory_file(b"disposable") as fd:
            self.assertEqual(os.fstat(fd).st_mode & 0o777, 0o600)
            self.assertEqual(os.read(fd, 100), b"disposable")
            with self.assertRaises(OSError) as error:
                os.write(fd, b"change")
            self.assertEqual(error.exception.errno, errno.EPERM)
        with self.assertRaises(OSError):
            os.fstat(fd)

    def test_descriptor_closes_on_failure(self) -> None:
        fd = -1
        with self.assertRaises(ValueError):
            with module.memory_file(b"disposable") as fd:
                raise ValueError("disposable failure")
        with self.assertRaises(OSError):
            os.fstat(fd)

    def test_generation_passes_only_descriptor_and_public_arguments(self) -> None:
        with patch.object(
            module.secrets, "capture_bundle", return_value=b"output"
        ) as capture:
            self.assertEqual(
                module.generate("/abs/talosctl", b"disposable", "controlplane"),
                b"output",
            )
        argv = capture.call_args.args[0]
        (fd,) = capture.call_args.kwargs["pass_fds"]
        self.assertEqual(argv[argv.index("--with-secrets") + 1], f"/proc/self/fd/{fd}")
        self.assertEqual(argv[-2:], ["--output", "-"])
        self.assertNotIn("disposable", " ".join(argv))
        with self.assertRaises(OSError):
            os.fstat(fd)

    def test_validation_failure_closes_descriptor(self) -> None:
        with patch.object(
            module.subprocess, "run", side_effect=subprocess.CalledProcessError(1, [])
        ) as run:
            with self.assertRaises(subprocess.CalledProcessError):
                module.validate_machine("/abs/talosctl", b"disposable")
        (fd,) = run.call_args.kwargs["pass_fds"]
        with self.assertRaises(OSError):
            os.fstat(fd)

    def test_client_metadata_requires_admin_context_and_unexpired_certificate(
        self,
    ) -> None:
        valid = {
            "context": module.CLUSTER,
            "roles": ["os:admin"],
            "certNotAfter": "2999-01-01",
        }
        for info, succeeds in [
            (valid, True),
            ({**valid, "roles": ["os:reader"]}, False),
            ({**valid, "context": "another-cluster"}, False),
            ({**valid, "certNotAfter": "2000-01-01"}, False),
        ]:
            with (
                self.subTest(info=info),
                patch.object(
                    module.secrets,
                    "capture_bundle",
                    return_value=json.dumps(info).encode(),
                ),
            ):
                if succeeds:
                    module.validate_client("/abs/talosctl", b"disposable")
                else:
                    with self.assertRaises(ValueError):
                        module.validate_client("/abs/talosctl", b"disposable")


if __name__ == "__main__":
    unittest.main()
