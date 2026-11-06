"""Generate-once and pipe-only recovery for the Trust Talos secrets bundle.

No secret-bearing machine configuration or apply functionality is provided here.
"""

import argparse
import ctypes
import logging
import os
import re
import resource
import stat
import subprocess
import sys
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
        r"(?m)^talos:[ \\t]*\\n[ \\t]+version:[ \\t]*(v[0-9]+\\.[0-9]+\\.[0-9]+)[ \\t]*$",
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


def require_private_repository() -> None:
    if not RECORD.parent.is_dir() or RECORD.parent.is_symlink():
        raise ValueError("Private wrapped-record submodule is not initialized")
    if RECORD.parent.resolve() != (ROOT / "secrets/wrapped").resolve():
        raise ValueError("Unexpected record directory")


def check_version(talosctl: str) -> None:
    response = subprocess.run(
        [talosctl, "version", "--client", "--short"],
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        check=True,
        timeout=15,
    )
    pin = talos_version().encode("ascii")
    if re.search(rb"(?<![a-zA-Z0-9.])" + re.escape(pin) + rb"(?![a-zA-Z0-9.])", response.stdout) is None:
        raise ValueError("Talos CLI version does not match the cluster pin")


def generate(talosctl: str) -> bytes:
    response = subprocess.run(
        [
            talosctl,
            "gen",
            "secrets",
            "--talos-version",
            talos_version(),
            "--output-file",
            "-",
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        check=True,
        timeout=60,
    )
    if not 0 < len(response.stdout) <= MAX_SECRETS:
        raise ValueError("Invalid Talos secret bundle size")
    return response.stdout


def initialize(talosctl: str, wrap_cli: str) -> None:
    if os.path.lexists(RECORD):
        raise FileExistsError("Talos bootstrap record already exists")
    check_version(talosctl)
    plaintext = generate(talosctl)
    # homelab-wrap verifies the AEAD record and creates ciphertext exclusively.
    subprocess.run(
        [
            wrap_cli,
            "--key-id",
            KEY_ID,
            "--root-key",
            ROOT_KEY,
            "--stdin",
            "--output",
            str(RECORD),
        ],
        input=plaintext,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=True,
        timeout=180,
    )
    print("Verified encrypted Trust bootstrap record created.", file=sys.stderr)


def require_pipe() -> None:
    mode = os.fstat(sys.stdout.fileno()).st_mode
    if not (stat.S_ISFIFO(mode) or stat.S_ISSOCK(mode)):
        raise ValueError("Plaintext recovery requires a pipe or socket")


def recover(unwrap_cli: str) -> None:
    require_pipe()
    if not RECORD.is_file() or RECORD.is_symlink():
        raise FileNotFoundError("Talos bootstrap record missing")
    process = subprocess.Popen(
        [
            unwrap_cli,
            "--key-id",
            KEY_ID,
            "--root-key",
            ROOT_KEY,
            "--input",
            str(RECORD),
            "--stdout",
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
    )
    try:
        assert process.stdout is not None
        total = 0
        while chunk := process.stdout.read(65536):
            total += len(chunk)
            if total > MAX_SECRETS:
                raise ValueError("Recovered bundle too large")
            sys.stdout.buffer.write(chunk)
        sys.stdout.buffer.flush()
        if process.wait(timeout=180):
            raise RuntimeError("Unwrap unsuccessful")
    finally:
        if process.poll() is None:
            process.kill()
            process.wait()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("init", "recover"))
    parser.add_argument("--talosctl", type=Path)
    parser.add_argument("--wrap", type=Path)
    parser.add_argument("--unwrap", type=Path)
    args = parser.parse_args()
    try:
        harden()
        require_private_repository()
        if args.action == "init":
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
            "private record, tool versions, swap, output pipe, token and touch.",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
