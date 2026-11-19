"""Enroll the Trust OpenTofu AES key and serve OpenTofu external key requests."""

import argparse
import base64
import hmac
import json
import os
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import trust_talos_secrets as secrets  # noqa: E402

KEY_ID = "homelab/v1/trust/opentofu/state/infrastructure/r1"
RECORD = secrets.ROOT / "secrets/wrapped/trust-opentofu-state-r1.json"
KEY_BYTES = 32
METADATA = {"external_data": {"key_id": KEY_ID}}


def recover(unwrap: str) -> bytes:
    with secrets.hsm_progress_terminal() as terminal:
        key = secrets.recover_bundle(
            unwrap, record=RECORD, key_id=KEY_ID, stderr=terminal
        )
    if len(key) != KEY_BYTES:
        raise ValueError("Expected a 32-byte OpenTofu AES key")
    return key


def provide(unwrap: str) -> None:
    secrets.require_pipe()
    print('{"magic":"OpenTofu-External-Key-Provider","version":1}', flush=True)
    request: object = json.load(sys.stdin)
    if request is not None and request != METADATA:
        raise ValueError("Unexpected OpenTofu state key metadata")
    encoded = base64.b64encode(recover(unwrap)).decode("ascii")
    keys = {"encryption_key": encoded}
    if request is not None:
        keys["decryption_key"] = encoded
    print(json.dumps({"keys": keys, "meta": METADATA}), flush=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("enroll", "verify", "provide"))
    args = parser.parse_args()
    try:
        secrets.harden()
        secrets.require_private_repository(record=RECORD)
        bin_dir = Path(sys.executable).parent
        unwrap = secrets.executable(bin_dir / "homelab-unwrap", "homelab-unwrap")
        if args.action == "provide":
            provide(unwrap)
        elif args.action == "verify":
            print("Touch the YubiKey to recover the Trust OpenTofu key.", flush=True)
            recover(unwrap)
            print("PASS: wrapped Trust OpenTofu AES key recovered.")
        else:
            wrap = secrets.executable(bin_dir / "homelab-wrap", "homelab-wrap")
            key = os.urandom(KEY_BYTES)
            print("Touch the YubiKey to wrap and verify the OpenTofu key.", flush=True)
            with secrets.hsm_progress_terminal() as terminal:
                secrets.wrap_bundle(
                    key, wrap, record=RECORD, key_id=KEY_ID, stderr=terminal
                )
            print("Touch the YubiKey again for independent recovery.", flush=True)
            if not hmac.compare_digest(key, recover(unwrap)):
                raise ValueError("Independently recovered OpenTofu key did not match")
            print("PASS: Trust OpenTofu AES key wrapped and independently recovered.")
    except FileExistsError:
        print("Record already exists. Run tofu-key-verify.", file=sys.stderr)
        return 1
    except secrets.PreflightError as exc:
        print(f"Trust OpenTofu key preflight failed: {exc}", file=sys.stderr)
        return 1
    except (
        OSError,
        RuntimeError,
        ValueError,
        subprocess.SubprocessError,
        KeyboardInterrupt,
    ):
        print(
            "Trust OpenTofu key operation failed. Check the wrapped record and YubiKey.",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
