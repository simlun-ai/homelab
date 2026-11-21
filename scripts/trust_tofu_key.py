"""Enroll the Trust OpenTofu AES key and serve OpenTofu external key requests."""

import argparse
import base64
import hmac
import json
import os
import socket
import subprocess
import sys
from enum import StrEnum
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import trust_talos_secrets as secrets  # noqa: E402

KEY_BYTES = 32


class StateScope(StrEnum):
    INFRASTRUCTURE = "infrastructure"
    WORKLOAD = "workload"

    @property
    def key_id(self) -> str:
        return f"homelab/v1/trust/opentofu/state/{self.value}/r1"

    @property
    def record(self) -> Path:
        name = (
            "trust-opentofu-state-r1.json"
            if self is StateScope.INFRASTRUCTURE
            else "trust-opentofu-workload-state-r1.json"
        )
        return secrets.ROOT / "secrets/wrapped" / name


def recover(unwrap: str, scope: StateScope) -> bytes:
    with secrets.hsm_progress_terminal() as terminal:
        key = secrets.recover_bundle(
            unwrap, record=scope.record, key_id=scope.key_id, stderr=terminal
        )
    if len(key) != KEY_BYTES:
        raise ValueError("Expected a 32-byte OpenTofu AES key")
    return key


def read_session_key(address: Path) -> bytes:
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as channel:
        channel.settimeout(5)
        channel.connect(str(address))
        with channel.makefile("rb") as response:
            key = response.read(KEY_BYTES + 1)
    if len(key) != KEY_BYTES:
        raise ValueError("Invalid OpenTofu key session response")
    return key


def provide(address: Path, scope: StateScope) -> None:
    secrets.require_pipe()
    print('{"magic":"OpenTofu-External-Key-Provider","version":1}', flush=True)
    request: object = json.load(sys.stdin)
    metadata = {"external_data": {"key_id": scope.key_id}}
    if request is not None and request != metadata:
        raise ValueError("Unexpected OpenTofu state key metadata")
    encoded = base64.b64encode(read_session_key(address)).decode("ascii")
    keys = {"encryption_key": encoded}
    if request is not None:
        keys["decryption_key"] = encoded
    print(json.dumps({"keys": keys, "meta": metadata}), flush=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("enroll", "verify", "provide"))
    parser.add_argument("--socket", type=Path)
    parser.add_argument(
        "--scope",
        type=StateScope,
        choices=tuple(StateScope),
        default=StateScope.INFRASTRUCTURE,
    )
    args = parser.parse_args()
    if (args.action == "provide") != (args.socket is not None):
        parser.error("--socket is required only for provide")
    scope = StateScope(args.scope)
    try:
        secrets.harden()
        if args.socket is not None:
            provide(args.socket, scope)
            return 0
        secrets.require_private_repository(record=scope.record)
        bin_dir = Path(sys.executable).parent
        unwrap = secrets.executable(bin_dir / "homelab-unwrap", "homelab-unwrap")
        if args.action == "verify":
            print("Touch the YubiKey to recover the Trust OpenTofu key.", flush=True)
            recover(unwrap, scope)
            print("PASS: wrapped Trust OpenTofu AES key recovered.")
        else:
            wrap = secrets.executable(bin_dir / "homelab-wrap", "homelab-wrap")
            key = os.urandom(KEY_BYTES)
            print("Touch the YubiKey to wrap and verify the OpenTofu key.", flush=True)
            with secrets.hsm_progress_terminal() as terminal:
                secrets.wrap_bundle(
                    key, wrap, record=scope.record, key_id=scope.key_id, stderr=terminal
                )
            print("Touch the YubiKey again for independent recovery.", flush=True)
            if not hmac.compare_digest(key, recover(unwrap, scope)):
                raise ValueError("Independently recovered OpenTofu key did not match")
            print("PASS: Trust OpenTofu AES key wrapped and independently recovered.")
    except FileExistsError:
        print(
            "Record already exists. Run the matching key verification.", file=sys.stderr
        )
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
