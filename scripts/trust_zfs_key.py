"""Enroll or verify the wrapped key for the Trust ZFS encryption root."""

import argparse
import hmac
import os
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import trust_talos_secrets as secrets  # noqa: E402

KEY_ID = "homelab/v1/trust/zfs/trust-cp1/trust-data/root/r1"
RECORD = secrets.ROOT / "secrets/wrapped/trust-data-zfs-r1.json"
KEY_BYTES = 32


def recover(unwrap: str) -> bytes:
    key = secrets.recover_bundle(unwrap, record=RECORD, key_id=KEY_ID)
    if len(key) != KEY_BYTES:
        raise ValueError("Wrapped ZFS key must recover exactly 32 bytes")
    return key


def enroll(wrap: str, unwrap: str) -> None:
    if os.path.lexists(RECORD):
        raise FileExistsError("ZFS key record already exists")
    key = os.urandom(KEY_BYTES)
    print("Touch the YubiKey to wrap and verify the new ZFS key.", flush=True)
    secrets.wrap_bundle(key, wrap, record=RECORD, key_id=KEY_ID)
    print("Touch the YubiKey again for independent recovery.", flush=True)
    if not hmac.compare_digest(key, recover(unwrap)):
        raise ValueError("Independently recovered ZFS key did not match")
    print("PASS: ZFS key wrapped and independently recovered.")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("enroll", "verify"))
    parser.add_argument("--wrap", type=Path)
    parser.add_argument("--unwrap", type=Path, required=True)
    args = parser.parse_args()
    if (args.action == "enroll") != (args.wrap is not None):
        parser.error("--wrap is required only for enrollment")
    try:
        secrets.harden()
        secrets.require_private_repository(record=RECORD)
        unwrap = secrets.executable(args.unwrap, "homelab-unwrap")
        if args.wrap is not None:
            enroll(secrets.executable(args.wrap, "homelab-wrap"), unwrap)
        else:
            if not RECORD.is_file() or RECORD.is_symlink():
                raise FileNotFoundError("ZFS key record missing")
            print("Touch the YubiKey to verify ZFS key recovery.", flush=True)
            recover(unwrap)
            print("PASS: wrapped ZFS key recovered as 32 bytes.")
    except FileExistsError:
        print("ZFS record already exists. Use zfs-key-verify.", file=sys.stderr)
        return 1
    except secrets.PreflightError as exc:
        print(f"ZFS key preflight failed: {exc}", file=sys.stderr)
        return 1
    except (
        OSError,
        RuntimeError,
        ValueError,
        subprocess.SubprocessError,
        KeyboardInterrupt,
    ):
        print(
            "ZFS key operation failed. If a record was written, inspect its status "
            "and verify it before retrying enrollment.",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
