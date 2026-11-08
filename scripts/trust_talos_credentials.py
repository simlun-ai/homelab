"""Rehearse native 24-hour Talos client issuance on verified tmpfs only."""

import argparse
import os
import resource
import shutil
import signal
import stat
import subprocess
import sys
import tempfile
from collections.abc import Generator
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import serialization
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID

sys.path.insert(0, str(Path(__file__).resolve().parent))
import trust_talos_config as config

MAX_FILE = 1024 * 1024
CLIENT_HOURS = 24
FILES = {
    "ca.crt",
    "ca.key",
    "ca.sha256",
    "client.key",
    "client.csr",
    "client.crt",
    "talosconfig",
}


def require_tmpfs(fd: int) -> None:
    """Match the held descriptor's mount ID, rather than a mutable pathname."""
    fields = Path(f"/proc/self/fdinfo/{fd}").read_text().splitlines()
    ids = [line.split()[1] for line in fields if line.startswith("mnt_id:")]
    if len(ids) == 1:
        for line in Path("/proc/self/mountinfo").read_text().splitlines():
            before, separator, after = line.partition(" - ")
            if (
                separator
                and before.split()[0] == ids[0]
                and after.split()[0] == "tmpfs"
            ):
                return
    raise config.secrets.PreflightError("RAM root must be on a verifiable tmpfs mount")


@contextmanager
def ram_directory(root: Path) -> Generator[tuple[Path, int]]:
    base = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)
    name: str | None = None
    fd: int | None = None
    try:
        require_tmpfs(base)
        info = os.fstat(base)
        if info.st_uid not in (0, os.geteuid()) or (
            info.st_mode & 0o022 and not info.st_mode & stat.S_ISVTX
        ):
            raise config.secrets.PreflightError(
                "RAM root must have trusted ownership and safe directory permissions"
            )
        name = Path(
            tempfile.mkdtemp(prefix="trust-credentials-", dir=f"/proc/self/fd/{base}")
        ).name
        fd = os.open(
            name,
            os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC,
            dir_fd=base,
        )
        require_tmpfs(fd)
        info = os.fstat(fd)
        if info.st_uid != os.geteuid() or info.st_mode & 0o777 != 0o700:
            raise config.secrets.PreflightError(
                "Private RAM workspace must be owned by the operator with mode 0700"
            )
        path = Path(f"/proc/self/fd/{fd}")
        print(f"Protected RAM workspace: {os.readlink(path)}", flush=True)
        yield path, fd
    finally:
        try:
            if name is not None:
                shutil.rmtree(name, dir_fd=base)
        finally:
            if fd is not None:
                os.close(fd)
            os.close(base)


@contextmanager
def file_limit() -> Generator[None]:
    previous = resource.getrlimit(resource.RLIMIT_FSIZE)
    soft = (
        MAX_FILE
        if previous[0] == resource.RLIM_INFINITY
        else min(previous[0], MAX_FILE)
    )
    resource.setrlimit(resource.RLIMIT_FSIZE, (soft, previous[1]))
    try:
        yield
    finally:
        resource.setrlimit(resource.RLIMIT_FSIZE, previous)


def audit(path: Path) -> None:
    for entry in path.iterdir():
        info = entry.lstat()
        if (
            entry.name not in FILES
            or not stat.S_ISREG(info.st_mode)
            or info.st_uid != os.geteuid()
            or info.st_mode & 0o077
            or info.st_size > MAX_FILE
        ):
            raise RuntimeError("Unexpected file, permissions or size in RAM workspace")


def run_native(talosctl: str, args: list[str], path: Path, fd: int) -> None:
    env = {
        **os.environ,
        "HOME": str(path),
        "TMPDIR": str(path),
        "XDG_CACHE_HOME": str(path),
    }
    env.pop("TALOSCONFIG", None)
    print(f"Native step: {args[0]} {args[1]}", flush=True)
    with file_limit():
        subprocess.run(
            [talosctl, *args],
            cwd=path,
            env=env,
            pass_fds=(fd,),
            umask=0o077,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=60,
            check=True,
        )
    audit(path)


def read_file(path: Path) -> bytes:
    with path.open("rb") as source:
        value = source.read(MAX_FILE + 1)
    if not 0 < len(value) <= MAX_FILE:
        raise ValueError("Invalid RAM artifact size")
    return value


def write_file(path: Path, value: bytes) -> None:
    if not 0 < len(value) <= MAX_FILE:
        raise ValueError("Invalid input size")
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "wb") as target:
        target.write(value)


def verify_client(
    ca_pem: bytes, crt_pem: bytes, key_pem: bytes, before: datetime, after: datetime
) -> None:
    ca = x509.load_pem_x509_certificate(ca_pem)
    crt = x509.load_pem_x509_certificate(crt_pem)
    # Talos labels PKCS#8 Ed25519 keys with a legacy PEM armor name.
    # Normalize only that armor for the standard parser, keeping DER unchanged.
    key_pem = key_pem.replace(
        b"-----BEGIN ED25519 PRIVATE KEY-----", b"-----BEGIN PRIVATE KEY-----"
    ).replace(b"-----END ED25519 PRIVATE KEY-----", b"-----END PRIVATE KEY-----")
    key = serialization.load_pem_private_key(key_pem, password=None)
    crt.verify_directly_issued_by(ca)
    if not ca.extensions.get_extension_for_class(x509.BasicConstraints).value.ca:
        raise ValueError("Issuer is not a CA")
    if (
        ca.not_valid_before_utc > before
        or ca.not_valid_after_utc < crt.not_valid_after_utc
    ):
        raise ValueError("Client validity exceeds issuer validity")
    encoding = serialization.Encoding.DER
    form = serialization.PublicFormat.SubjectPublicKeyInfo
    if key.public_key().public_bytes(encoding, form) != crt.public_key().public_bytes(
        encoding, form
    ):
        raise ValueError("Client private key does not match certificate")
    if [
        entry.value
        for entry in crt.subject.get_attributes_for_oid(NameOID.ORGANIZATION_NAME)
    ] != ["os:admin"]:
        raise ValueError("Unexpected client roles")
    if (
        ExtendedKeyUsageOID.CLIENT_AUTH
        not in crt.extensions.get_extension_for_class(x509.ExtendedKeyUsage).value
    ):
        raise ValueError("Missing client-auth usage")
    ttl = timedelta(hours=CLIENT_HOURS)
    if (
        not before + ttl - timedelta(seconds=1)
        <= crt.not_valid_after_utc
        <= after + ttl + timedelta(seconds=1)
    ):
        raise ValueError("Unexpected client certificate expiry")


def issue(talosctl: str, ca_crt: bytes, ca_key: bytes, root: Path) -> bytes:
    """Issue from supplied CA material; never generate a replacement authority."""
    with ram_directory(root) as (path, fd):
        write_file(path / "ca.crt", ca_crt)
        write_file(path / "ca.key", ca_key)
        run_native(talosctl, ["gen", "key", "--name", str(path / "client")], path, fd)
        run_native(
            talosctl,
            [
                "gen",
                "csr",
                "--key",
                str(path / "client.key"),
                "--ip",
                "127.0.0.1",
                "--roles",
                "os:admin",
            ],
            path,
            fd,
        )
        before = datetime.now(UTC)
        run_native(
            talosctl,
            [
                "gen",
                "crt",
                "--ca",
                str(path / "ca"),
                "--csr",
                str(path / "client.csr"),
                "--name",
                str(path / "client"),
                "--hours",
                str(CLIENT_HOURS),
            ],
            path,
            fd,
        )
        after = datetime.now(UTC)
        print("Verifying issued certificate policy.", flush=True)
        verify_client(
            ca_crt,
            read_file(path / "client.crt"),
            read_file(path / "client.key"),
            before,
            after,
        )
        run_native(
            talosctl,
            [
                "config",
                "add",
                config.CLUSTER,
                "--ca",
                str(path / "ca.crt"),
                "--crt",
                str(path / "client.crt"),
                "--key",
                str(path / "client.key"),
                "--talosconfig",
                str(path / "talosconfig"),
            ],
            path,
            fd,
        )
        run_native(
            talosctl,
            [
                "config",
                "context",
                config.CLUSTER,
                "--talosconfig",
                str(path / "talosconfig"),
            ],
            path,
            fd,
        )
        client = read_file(path / "talosconfig")
        print("Inspecting assembled client configuration.", flush=True)
        config.validate_client(talosctl, client)
        return client


def rehearse(talosctl: str, root: Path) -> None:
    print("Generating a disposable CA with native Talos tooling on tmpfs.", flush=True)
    with ram_directory(root) as (path, fd):
        run_native(talosctl, ["gen", "ca", "--organization", "ca"], path, fd)
        ca_crt, ca_key = read_file(path / "ca.crt"), read_file(path / "ca.key")
    print(
        "Issuing a 24-hour administration credential from the supplied CA.", flush=True
    )
    issue(talosctl, ca_crt, ca_key, root)
    print(
        "PASS: issuer signature, client key, os:admin role, client-auth usage and 24-hour expiry."
    )
    print("PASS: native talosconfig assembly and inspection; RAM workspaces removed.")


def interrupted(_signum: int, _frame: object) -> None:
    raise InterruptedError("Credential operation interrupted")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--talosctl", required=True, type=Path)
    parser.add_argument("--ram-root", type=Path, default=Path("/dev/shm"))
    args = parser.parse_args()
    try:
        config.secrets.harden()
        signal.signal(signal.SIGTERM, interrupted)
        signal.signal(signal.SIGHUP, interrupted)
        rehearse(config.secrets.executable(args.talosctl, "talosctl"), args.ram_root)
    except config.secrets.PreflightError as exc:
        print(f"Credential preflight failed: {exc}", file=sys.stderr)
        return 1
    except (Exception, KeyboardInterrupt):
        print(
            "Credential rehearsal failed; details suppressed. Check the last stage and RAM workspace availability.",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
