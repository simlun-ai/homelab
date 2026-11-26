"""Protected native Talos secret generation and wrapped-record access."""

import ctypes
import logging
import os
import re
import resource
import selectors
import subprocess
import sys
import time
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path

ROOT_KEY = "golden-1"
MAX_SECRETS = 1024 * 1024


def cluster_version(component: str, scope: Path) -> str:
    """Read an authoritative cluster release pin without another version constant."""
    content = (scope / "versions.yaml").read_text(encoding="utf-8")
    match = re.search(
        rf"(?m)^{re.escape(component)}:[ \t]*\n"
        r"[ \t]+version:[ \t]*(v[0-9]+\.[0-9]+\.[0-9]+)[ \t]*$",
        content,
    )
    if match is None:
        raise ValueError(f"Missing or invalid {scope.name} release pin")
    return match.group(1)


class PreflightError(ValueError):
    """A deliberately public diagnostic containing no subprocess output."""


def harden() -> None:
    if sys.platform != "linux":
        raise PreflightError("Linux is required")
    logging.disable(sys.maxsize)
    sys.dont_write_bytecode = True
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    libc = ctypes.CDLL(None, use_errno=True)
    if libc.prctl(4, 0, 0, 0, 0) != 0:
        raise PreflightError("Cannot disable process dumping")
    from homelab_secrets.swap import UnsafeSwapError, require_safe_swap

    try:
        require_safe_swap()
    except UnsafeSwapError as exc:
        raise PreflightError(str(exc)) from None


def executable(path: Path, label: str = "tool") -> str:
    if not path.is_absolute() or not path.is_file() or not os.access(path, os.X_OK):
        raise PreflightError(
            f"{label}: an existing absolute executable path is required"
        )
    return str(path)


def require_private_repository(*, root: Path, record: Path) -> None:
    directory = root / "secrets/wrapped"
    if (
        record.parent != directory
        or directory.is_symlink()
        or directory.parent.is_symlink()
        or not directory.is_dir()
    ):
        raise ValueError("Private wrapped-record submodule is not initialized")
    tracked = subprocess.run(
        ["git", "-C", str(root), "ls-files", "--stage", "--", "secrets/wrapped"],
        capture_output=True,
        check=True,
        timeout=10,
    ).stdout.splitlines()
    if len(tracked) != 1 or not tracked[0].startswith(b"160000 "):
        raise ValueError("Wrapped-record path must be a tracked submodule")
    toplevel = (
        subprocess.run(
            ["git", "-C", str(directory), "rev-parse", "--show-toplevel"],
            capture_output=True,
            check=True,
            timeout=10,
        )
        .stdout.decode()
        .strip()
    )
    if Path(toplevel).resolve() != directory.resolve():
        raise ValueError("Private wrapped-record submodule is not initialized")


@contextmanager
def hsm_progress_terminal() -> Generator[int]:
    """Route public HSM progress to the operator even when stderr is captured."""
    try:
        fd = os.open("/dev/tty", os.O_WRONLY | os.O_CLOEXEC)
    except OSError:
        yield subprocess.DEVNULL
        return
    try:
        yield fd
    finally:
        os.close(fd)


def capture_bundle(
    argv: list[str],
    timeout: float,
    *,
    pass_fds: tuple[int, ...] = (),
    stderr: int = subprocess.DEVNULL,
) -> bytes:
    """Bound output and elapsed time; release no bytes until the child succeeds."""
    deadline = time.monotonic() + timeout
    process = subprocess.Popen(
        argv, stdout=subprocess.PIPE, stderr=stderr, pass_fds=pass_fds
    )
    try:
        assert process.stdout is not None
        with process.stdout, selectors.DefaultSelector() as selector:
            selector.register(process.stdout, selectors.EVENT_READ)
            output = bytearray()
            while True:
                remaining = deadline - time.monotonic()
                if remaining <= 0 or not selector.select(remaining):
                    raise TimeoutError("Secret subprocess timed out")
                chunk = os.read(process.stdout.fileno(), 65536)
                if not chunk:
                    break
                if len(output) + len(chunk) > MAX_SECRETS:
                    raise ValueError("Secret bundle too large")
                output.extend(chunk)
            if process.wait(timeout=max(0, deadline - time.monotonic())):
                raise RuntimeError("Secret subprocess failed")
            if not output:
                raise ValueError("Empty secret bundle")
            return bytes(output)
    finally:
        if process.poll() is None:
            process.kill()
        process.wait()


def generate_secrets(talosctl: str, version: str) -> bytes:
    return capture_bundle(
        [
            talosctl,
            "gen",
            "secrets",
            "--talos-version",
            version,
            "--output-file",
            "-",
        ],
        timeout=60,
    )


def wrap_bundle(
    plaintext: bytes,
    wrap_cli: str,
    *,
    record: Path,
    key_id: str,
    stderr: int = subprocess.DEVNULL,
) -> None:
    if os.path.lexists(record):
        raise FileExistsError("Talos bootstrap record already exists")
    # homelab-wrap verifies the AEAD record and creates ciphertext exclusively.
    subprocess.run(
        [
            wrap_cli,
            "--key-id",
            key_id,
            "--root-key",
            ROOT_KEY,
            "--stdin",
            "--output",
            str(record),
        ],
        input=plaintext,
        stdout=subprocess.DEVNULL,
        stderr=stderr,
        check=True,
        timeout=180,
    )


def recover_bundle(
    unwrap_cli: str, *, record: Path, key_id: str, stderr: int = subprocess.DEVNULL
) -> bytes:
    if not record.is_file() or record.is_symlink():
        raise FileNotFoundError("Talos bootstrap record missing")
    return capture_bundle(
        [
            unwrap_cli,
            "--key-id",
            key_id,
            "--root-key",
            ROOT_KEY,
            "--input",
            str(record),
            "--stdout",
        ],
        timeout=180,
        stderr=stderr,
    )
