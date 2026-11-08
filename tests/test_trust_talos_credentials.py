"""RAM workspace checks and certificate policy using public dummy fixtures."""

import importlib.util
import os
import resource
import subprocess
import tempfile
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import call, patch

from cryptography import x509
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ed25519
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/trust_talos_credentials.py"
spec = importlib.util.spec_from_file_location("trust_talos_credentials", SCRIPT)
assert spec is not None and spec.loader is not None
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def fixtures(
    hours: int = 24, role: str = "os:admin"
) -> tuple[bytes, bytes, bytes, datetime]:
    # Fixed, PUBLIC seeds. These keys are not secret or valid cluster identities.
    ca_key = ed25519.Ed25519PrivateKey.from_private_bytes(bytes(range(32)))
    key = ed25519.Ed25519PrivateKey.from_private_bytes(bytes(range(32, 64)))
    now = datetime(2026, 11, 8, tzinfo=UTC)
    issuer = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "PUBLIC fixture")])
    ca = (
        x509.CertificateBuilder()
        .subject_name(issuer)
        .issuer_name(issuer)
        .public_key(ca_key.public_key())
        .serial_number(1)
        .not_valid_before(now - timedelta(minutes=1))
        .not_valid_after(now + timedelta(days=365))
        .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
        .sign(ca_key, None)
    )
    crt = (
        x509.CertificateBuilder()
        .subject_name(x509.Name([x509.NameAttribute(NameOID.ORGANIZATION_NAME, role)]))
        .issuer_name(issuer)
        .public_key(key.public_key())
        .serial_number(2)
        .not_valid_before(now)
        .not_valid_after(now + timedelta(hours=hours))
        .add_extension(
            x509.ExtendedKeyUsage([ExtendedKeyUsageOID.CLIENT_AUTH]), critical=False
        )
        .sign(ca_key, None)
    )
    return (
        ca.public_bytes(serialization.Encoding.PEM),
        crt.public_bytes(serialization.Encoding.PEM),
        key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        ),
        now,
    )


class CredentialTests(unittest.TestCase):
    def test_mount_identity_must_be_tmpfs(self) -> None:
        def contents(path: Path) -> str:
            if "fdinfo" in str(path):
                return "mnt_id:\t123\n"
            return "123 1 0:3 / /ram rw - tmpfs tmpfs rw\n"

        with patch.object(Path, "read_text", contents):
            module.require_tmpfs(42)
        with patch.object(Path, "read_text", return_value="mnt_id:\t123\n"):
            with self.assertRaises(module.config.secrets.PreflightError):
                module.require_tmpfs(42)

    def test_unverified_directory_is_rejected_before_creating_workspace(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with patch.object(
                module,
                "require_tmpfs",
                side_effect=module.config.secrets.PreflightError("Not RAM"),
            ):
                with self.assertRaises(module.config.secrets.PreflightError):
                    with module.ram_directory(root):
                        self.fail("Unexpected admission")
            self.assertEqual(list(root.iterdir()), [])

    def test_workspace_is_private_and_removed_on_failure(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            fd = -1
            # Public fixture only: mock mount admission, never generate real keys.
            with patch.object(module, "require_tmpfs"), self.assertRaises(ValueError):
                with module.ram_directory(root) as (path, fd):
                    self.assertEqual(os.fstat(fd).st_mode & 0o777, 0o700)
                    module.write_file(path / "client.key", b"PUBLIC fixture")
                    module.audit(path)
                    raise ValueError("fixture failure")
            self.assertEqual(list(root.iterdir()), [])
            with self.assertRaises(OSError):
                os.fstat(fd)

    def test_writable_parent_without_sticky_bit_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            root.chmod(0o777)
            with (
                patch.object(module, "require_tmpfs"),
                self.assertRaises(module.config.secrets.PreflightError),
            ):
                with module.ram_directory(root):
                    self.fail("Unexpected admission")

    def test_file_safety_and_exclusive_creation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / "client.key"
            module.write_file(path, b"PUBLIC fixture")
            with self.assertRaises(FileExistsError):
                module.write_file(path, b"replacement")
            self.assertEqual(module.read_file(path), b"PUBLIC fixture")
            path.chmod(0o644)
            with self.assertRaises(RuntimeError):
                module.audit(root)
            path.unlink()
            path.symlink_to(root / "missing")
            with self.assertRaises(RuntimeError):
                module.audit(root)

    def test_resource_limit_restored_on_failure(self) -> None:
        limits = (resource.RLIM_INFINITY, resource.RLIM_INFINITY)
        with (
            patch.object(module.resource, "getrlimit", return_value=limits),
            patch.object(module.resource, "setrlimit") as set_limit,
        ):
            with self.assertRaises(ValueError):
                with module.file_limit():
                    raise ValueError("fixture")
            self.assertEqual(
                set_limit.call_args_list,
                [
                    call(resource.RLIMIT_FSIZE, (module.MAX_FILE, limits[1])),
                    call(resource.RLIMIT_FSIZE, limits),
                ],
            )

    def test_native_process_uses_private_paths_and_suppressed_output(self) -> None:
        with (
            patch.object(module.subprocess, "run") as run,
            patch.object(module, "audit"),
            patch.object(module, "file_limit"),
        ):
            path = Path("/proc/self/fd/42")
            module.run_native("/abs/talosctl", ["gen", "ca"], path, 42)
            kwargs = run.call_args.kwargs
            self.assertEqual(kwargs["cwd"], path)
            self.assertEqual(kwargs["pass_fds"], (42,))
            self.assertEqual(kwargs["umask"], 0o077)
            self.assertEqual(kwargs["env"]["TMPDIR"], str(path))
            self.assertEqual(kwargs["stderr"], subprocess.DEVNULL)

    def test_certificate_role_key_and_ttl(self) -> None:
        ca, crt, key, now = fixtures()
        module.verify_client(ca, crt, key, now, now)
        native_key = key.replace(b"PRIVATE KEY", b"ED25519 PRIVATE KEY")
        module.verify_client(ca, crt, native_key, now, now)
        for hours, role in ((25, "os:admin"), (24, "os:reader")):
            ca, crt, key, now = fixtures(hours, role)
            with self.assertRaises(ValueError):
                module.verify_client(ca, crt, key, now, now)
        ca, crt, _, now = fixtures()
        other_key = ed25519.Ed25519PrivateKey.from_private_bytes(bytes([99]) * 32)
        encoded = other_key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
        with self.assertRaises(ValueError):
            module.verify_client(ca, crt, encoded, now, now)


if __name__ == "__main__":
    unittest.main()
