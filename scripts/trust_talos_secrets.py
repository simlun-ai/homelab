"""Generate-once and pipe-only recovery for the Trust Talos secrets bundle.

No secret-bearing machine configuration or apply functionality is provided here.
"""

import argparse
import base64
import ctypes
import hmac
import json
import logging
import os
import re
import resource
import selectors
import stat
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RECORD = ROOT / "secrets/wrapped/trust-talos-bootstrap.json"
KEY_ID = "homelab/v1/trust/talos/bootstrap/r1"
ROOT_KEY = "golden-1"
MAX_SECRETS = 1024 * 1024


def talos_version() -> str:
    """Read the authoritative Talos pin without a second version constant."""
    content = (ROOT / "clusters/trust/versions.yaml").read_text(encoding="utf-8")
    match = re.search(
        r"(?m)^talos:[ \t]*\n[ \t]+version:[ \t]*(v[0-9]+\.[0-9]+\.[0-9]+)[ \t]*$",
        content,
    )
    if match is None:
        raise ValueError("Missing or invalid Trust Talos version pin")
    return match.group(1)


def harden() -> None:
    if sys.platform != "linux":
        raise RuntimeError("Linux is required")
    logging.disable(sys.maxsize)
    sys.dont_write_bytecode = True
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    libc = ctypes.CDLL(None, use_errno=True)
    if libc.prctl(4, 0, 0, 0, 0) != 0:
        raise RuntimeError("Cannot disable process dumping")
    if Path("/proc/swaps").read_text(encoding="utf-8").splitlines()[1:]:
        raise RuntimeError("Swap must be disabled")


def executable(path: Path) -> str:
    if not path.is_absolute() or not path.is_file() or not os.access(path, os.X_OK):
        raise ValueError("Absolute executable path required")
    return str(path)


def require_private_repository(
    *, root: Path | None = None, record: Path | None = None
) -> None:
    root = ROOT if root is None else root
    record = RECORD if record is None else record
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


def capture_bundle(argv: list[str], timeout: float) -> bytes:
    """Bound output and elapsed time; release no bytes until the child succeeds."""
    deadline = time.monotonic() + timeout
    process = subprocess.Popen(argv, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
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


def generate(talosctl: str) -> bytes:
    return capture_bundle(
        [
            talosctl,
            "gen",
            "secrets",
            "--talos-version",
            talos_version(),
            "--output-file",
            "-",
        ],
        timeout=60,
    )


def initialize(talosctl: str, wrap_cli: str) -> None:
    if os.path.lexists(RECORD):
        raise FileExistsError("Talos bootstrap record already exists")
    plaintext = generate(talosctl)
    wrap_bundle(plaintext, wrap_cli, record=RECORD, key_id=KEY_ID)
    print("Verified encrypted Trust bootstrap record created.", file=sys.stderr)


def wrap_bundle(plaintext: bytes, wrap_cli: str, *, record: Path, key_id: str) -> None:
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
        stderr=subprocess.DEVNULL,
        check=True,
        timeout=180,
    )


def require_pipe() -> None:
    mode = os.fstat(sys.stdout.fileno()).st_mode
    if not (stat.S_ISFIFO(mode) or stat.S_ISSOCK(mode)):
        raise ValueError("Plaintext recovery requires a pipe or socket")


def recover_bundle(unwrap_cli: str, *, record: Path, key_id: str) -> bytes:
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
    )


def recover(unwrap_cli: str) -> None:
    require_pipe()
    plaintext = recover_bundle(unwrap_cli, record=RECORD, key_id=KEY_ID)
    sys.stdout.buffer.write(plaintext)
    sys.stdout.buffer.flush()


def rehearse(talosctl: str, wrap_cli: str, unwrap_cli: str) -> None:
    """Use only disposable identity material and an isolated ciphertext repository."""
    key_id = "homelab/v1/trust/talos/rehearsal/r1"
    with tempfile.TemporaryDirectory(prefix="trust-talos-rehearsal-") as directory:
        root = Path(directory)
        record = root / "secrets/wrapped/disposable.json"
        record.parent.mkdir(parents=True)
        for repository in (root, record.parent):
            subprocess.run(
                ["git", "init", "--quiet", str(repository)],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=True,
                timeout=10,
            )
        # An index-only gitlink fixture; no commits, remotes or real records.
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
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=True,
            timeout=10,
        )
        require_private_repository(root=root, record=record)
        plaintext = generate(talosctl)
        print(
            "Touch the YubiKey when it flashes for wrapping and verification.",
            flush=True,
        )
        wrap_bundle(plaintext, wrap_cli, record=record, key_id=key_id)
        encoded = record.read_bytes()
        print("Touch the YubiKey when it flashes for recovery.", flush=True)
        recovered = recover_bundle(unwrap_cli, record=record, key_id=key_id)
        if not hmac.compare_digest(plaintext, recovered):
            raise ValueError("Rehearsal round trip did not match")
        print("PASS: generated, wrapped and recovered identical disposable secrets.")
        try:
            wrap_bundle(plaintext, wrap_cli, record=record, key_id=key_id)
        except FileExistsError:
            pass
        else:
            raise ValueError("Rehearsal allowed an overwrite")
        if record.read_bytes() != encoded:
            raise ValueError("Rehearsal changed an existing record")
        print("PASS: existing record cannot be overwritten.")
        # Flip one ciphertext bit, preserving valid JSON and Base64 so this
        # exercises authenticated decryption rather than just record parsing.
        damaged: dict[str, object] = json.loads(encoded)
        ciphertext = damaged["ciphertext"]
        if not isinstance(ciphertext, str):
            raise ValueError("Unexpected rehearsal ciphertext")
        changed = bytearray(base64.b64decode(ciphertext, validate=True))
        changed[0] ^= 1
        damaged["ciphertext"] = base64.b64encode(changed).decode("ascii")
        record.write_text(json.dumps(damaged), encoding="utf-8")
        print("Touch the YubiKey when it flashes for the corruption check.", flush=True)
        try:
            recover_bundle(unwrap_cli, record=record, key_id=key_id)
        except RuntimeError:
            pass
        else:
            raise ValueError("Rehearsal accepted damaged ciphertext")
        print("PASS: damaged ciphertext cannot be recovered.")
        record.unlink()
        try:
            recover_bundle(unwrap_cli, record=record, key_id=key_id)
        except FileNotFoundError:
            pass
        else:
            raise ValueError("Rehearsal accepted a missing record")
        print("PASS: missing record is rejected.")
    print("PASS: rehearsal complete; temporary ciphertext repository removed.")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("init", "recover", "rehearse"))
    parser.add_argument("--talosctl", type=Path)
    parser.add_argument("--wrap", type=Path)
    parser.add_argument("--unwrap", type=Path)
    args = parser.parse_args()
    try:
        harden()
        if args.action != "rehearse":
            require_private_repository()
        if args.action == "rehearse":
            if args.talosctl is None or args.wrap is None or args.unwrap is None:
                raise ValueError("rehearse requires --talosctl, --wrap and --unwrap")
            rehearse(
                executable(args.talosctl),
                executable(args.wrap),
                executable(args.unwrap),
            )
        elif args.action == "init":
            if args.talosctl is None or args.wrap is None or args.unwrap is not None:
                raise ValueError("init requires --talosctl and --wrap only")
            initialize(executable(args.talosctl), executable(args.wrap))
        else:
            if (
                args.unwrap is None
                or args.talosctl is not None
                or args.wrap is not None
            ):
                raise ValueError("recover requires --unwrap only")
            recover(executable(args.unwrap))
    except (Exception, KeyboardInterrupt):
        # Never expose subprocess stderr: it may contain secret-bearing content.
        print(
            "Talos bootstrap operation failed; details suppressed. Check the "
            "private record, swap, output pipe, token and touch.",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
