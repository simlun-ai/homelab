"""Tool acquisition failure paths, using public disposable bytes only."""

import hashlib
import importlib.util
import io
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

SCRIPT = Path(__file__).resolve().parents[1] / "clusters/trust/tooling.py"
spec = importlib.util.spec_from_file_location("trust_tooling", SCRIPT)
assert spec is not None and spec.loader is not None
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class TrustToolingTests(unittest.TestCase):
    def test_checksum_failure_keeps_previous_binary_and_removes_download(self) -> None:
        with TemporaryDirectory() as directory:
            scope = Path(directory)
            binary = scope / "bin/talosctl"
            binary.parent.mkdir()
            binary.write_bytes(b"previous")
            with (
                patch.object(module, "SCOPE", scope),
                patch.object(
                    module.urllib.request, "urlopen", return_value=io.BytesIO(b"bad")
                ),
            ):
                with self.assertRaisesRegex(ValueError, "SHA-256"):
                    module.install("talosctl", "https://example.invalid/tool", "0" * 64)
            self.assertEqual(binary.read_bytes(), b"previous")
            self.assertEqual(list(binary.parent.iterdir()), [binary])

    def test_successful_download_is_verified_and_executable(self) -> None:
        content = b"disposable tool bytes"
        checksum = hashlib.sha256(content).hexdigest()
        with TemporaryDirectory() as directory:
            scope = Path(directory)
            binary = scope / "bin/talosctl"
            with (
                patch.object(module, "SCOPE", scope),
                patch.object(
                    module.urllib.request, "urlopen", return_value=io.BytesIO(content)
                ),
            ):
                module.install("talosctl", "https://example.invalid/tool", checksum)
            self.assertTrue(
                module.verified(binary, checksum, "https://example.invalid/tool")
            )
            self.assertFalse(
                module.verified(binary, checksum, "https://example.invalid/new-version")
            )
            binary.write_bytes(b"tampered")
            self.assertFalse(
                module.verified(binary, checksum, "https://example.invalid/tool")
            )

    def test_download_size_limit_cleans_up(self) -> None:
        with TemporaryDirectory() as directory:
            scope = Path(directory)
            with (
                patch.object(module, "SCOPE", scope),
                patch.object(module, "MAX_DOWNLOAD", 2),
                patch.object(
                    module.urllib.request, "urlopen", return_value=io.BytesIO(b"large")
                ),
            ):
                with self.assertRaisesRegex(ValueError, "too large"):
                    module.install("kubectl", "https://example.invalid/tool", "0" * 64)
            self.assertEqual(list((scope / "bin").iterdir()), [])

    def test_check_is_offline_and_rejects_missing_binaries(self) -> None:
        with TemporaryDirectory() as directory:
            with (
                patch.object(module, "SCOPE", Path(directory)),
                patch.object(module, "architecture", return_value="amd64"),
                patch.object(
                    module,
                    "specification",
                    return_value=("https://example.invalid", "0" * 64),
                ),
                patch.object(module.urllib.request, "urlopen") as download,
            ):
                with self.assertRaisesRegex(ValueError, "run make"):
                    module.tools("check")
                download.assert_not_called()

    def test_url_uses_scope_version_pin(self) -> None:
        with TemporaryDirectory() as directory:
            scope = Path(directory)
            (scope / "versions.yaml").write_text("talos:\n  version: v2.3.4\n")
            (scope / "toolchain.toml").write_text(
                '[talosctl]\nurl = "https://example.invalid/{version}/{arch}"\n'
                '[talosctl.sha256]\namd64 = "' + "1" * 64 + '"\n'
            )
            with patch.object(module, "SCOPE", scope):
                url, checksum = module.specification("talosctl", "amd64")
            self.assertEqual(url, "https://example.invalid/v2.3.4/amd64")
            self.assertEqual(checksum, "1" * 64)

    def test_verified_cache_is_reused_without_network(self) -> None:
        content = b"disposable"
        checksum = hashlib.sha256(content).hexdigest()
        url = "https://example.invalid/tool"
        with TemporaryDirectory() as directory:
            scope = Path(directory)
            binary = scope / "bin/talosctl"
            binary.parent.mkdir()
            binary.write_bytes(content)
            binary.chmod(0o755)
            binary.with_suffix(".source").write_text(url + "\n")
            with (
                patch.object(module, "SCOPE", scope),
                patch.object(module, "PINS", {"talosctl": "talos"}),
                patch.object(module, "architecture", return_value="amd64"),
                patch.object(module, "specification", return_value=(url, checksum)),
                patch.object(module, "version", return_value="v2.3.4"),
                patch.object(module.urllib.request, "urlopen") as download,
            ):
                module.tools("install")
                module.tools("check")
                download.assert_not_called()

    def test_symlinked_tool_directory_is_rejected(self) -> None:
        with TemporaryDirectory() as directory:
            scope = Path(directory)
            destination = scope / "elsewhere"
            destination.mkdir()
            (scope / "bin").symlink_to(destination, target_is_directory=True)
            with patch.object(module, "SCOPE", scope):
                with self.assertRaisesRegex(ValueError, "symlink"):
                    module.install("talosctl", "https://example.invalid", "0" * 64)

    def test_unsupported_platforms_fail(self) -> None:
        with patch.object(module.platform, "system", return_value="Darwin"):
            with self.assertRaisesRegex(ValueError, "Linux only"):
                module.architecture()
        with (
            patch.object(module.platform, "system", return_value="Linux"),
            patch.object(module.platform, "machine", return_value="mips"),
        ):
            with self.assertRaisesRegex(ValueError, "Unsupported"):
                module.architecture()


if __name__ == "__main__":
    unittest.main()
