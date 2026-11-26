"""Generate-once and pipe-only recovery for the Trust Talos secrets bundle.

No secret-bearing machine configuration or apply functionality is provided here.
"""

import argparse
import base64
import hmac
import json
import os
import stat
import subprocess
import sys
import tempfile
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from homelab.talos import bootstrap

MAX_SECRETS = bootstrap.MAX_SECRETS
ROOT_KEY = bootstrap.ROOT_KEY
PreflightError = bootstrap.PreflightError
capture_bundle = bootstrap.capture_bundle
executable = bootstrap.executable
harden = bootstrap.harden
hsm_progress_terminal = bootstrap.hsm_progress_terminal
recover_bundle = bootstrap.recover_bundle
wrap_bundle = bootstrap.wrap_bundle

ROOT = Path(__file__).resolve().parents[1]
RECORD = ROOT / "secrets/wrapped/trust-talos-bootstrap.json"
KEY_ID = "homelab/v1/trust/talos/bootstrap/r1"
REHEARSAL_KEY_ID = "homelab/v1/trust/talos/rehearsal/r1"


def cluster_version(component: str) -> str:
    return bootstrap.cluster_version(component, ROOT / "clusters/trust")


def talos_version() -> str:
    return cluster_version("talos")


def require_private_repository(
    *, root: Path | None = None, record: Path | None = None
) -> None:
    bootstrap.require_private_repository(
        root=ROOT if root is None else root,
        record=RECORD if record is None else record,
    )


def generate(talosctl: str) -> bytes:
    return bootstrap.generate_secrets(talosctl, talos_version())


def initialize(talosctl: str, wrap_cli: str) -> None:
    if os.path.lexists(RECORD):
        raise FileExistsError("Talos bootstrap record already exists")
    plaintext = generate(talosctl)
    wrap_bundle(plaintext, wrap_cli, record=RECORD, key_id=KEY_ID)
    print("Verified encrypted Trust bootstrap record created.", file=sys.stderr)


def require_pipe() -> None:
    mode = os.fstat(sys.stdout.fileno()).st_mode
    if not (stat.S_ISFIFO(mode) or stat.S_ISSOCK(mode)):
        raise ValueError("Plaintext recovery requires a pipe or socket")


def recover(unwrap_cli: str) -> None:
    require_pipe()
    plaintext = recover_bundle(unwrap_cli, record=RECORD, key_id=KEY_ID)
    sys.stdout.buffer.write(plaintext)
    sys.stdout.buffer.flush()


@contextmanager
def rehearsal_record() -> Generator[Path]:
    """Create and clean up an isolated repository containing ciphertext only."""
    print("Preparing isolated ciphertext repository.", flush=True)
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
        yield record


def rehearse(talosctl: str, wrap_cli: str, unwrap_cli: str) -> None:
    """Use only disposable identity material and an isolated ciphertext repository."""
    key_id = REHEARSAL_KEY_ID
    with rehearsal_record() as record:
        print("Generating disposable Talos secrets in memory.", flush=True)
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
    stage = "workstation safety checks"
    try:
        harden()
        stage = "private repository checks"
        if args.action != "rehearse":
            require_private_repository()
        stage = "executable selection"
        if args.action == "rehearse":
            if args.talosctl is None or args.wrap is None or args.unwrap is None:
                raise ValueError("rehearse requires --talosctl, --wrap and --unwrap")
            talosctl = executable(args.talosctl, "talosctl")
            wrap_cli = executable(args.wrap, "homelab-wrap")
            unwrap_cli = executable(args.unwrap, "homelab-unwrap")
            stage = "rehearsal (see the last progress message)"
            rehearse(talosctl, wrap_cli, unwrap_cli)
        elif args.action == "init":
            if args.talosctl is None or args.wrap is None or args.unwrap is not None:
                raise ValueError("init requires --talosctl and --wrap only")
            talosctl = executable(args.talosctl, "talosctl")
            wrap_cli = executable(args.wrap, "homelab-wrap")
            stage = "initialization"
            initialize(talosctl, wrap_cli)
        else:
            if (
                args.unwrap is None
                or args.talosctl is not None
                or args.wrap is not None
            ):
                raise ValueError("recover requires --unwrap only")
            unwrap_cli = executable(args.unwrap, "homelab-unwrap")
            stage = "recovery"
            recover(unwrap_cli)
    except PreflightError as exc:
        print(f"Talos bootstrap preflight failed: {exc}", file=sys.stderr)
        return 1
    except (Exception, KeyboardInterrupt):
        # Never expose subprocess stderr: it may contain secret-bearing content.
        print(
            f"Talos bootstrap operation failed during {stage}; details suppressed. "
            "Check the private record, swap, output pipe, token and touch.",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
