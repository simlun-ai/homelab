"""Enroll the Trust node key and authorize it over verified coordinator SSH."""

import argparse
import base64
import hmac
import json
import os
import subprocess
import sys
from pathlib import Path
from uuid import uuid4

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
import trust_talos_secrets as secrets  # noqa: E402
from homelab.trust_kms import registration  # noqa: E402
from trust_kms_acme_state_operator import exchange, tls_status  # noqa: E402

RECORD = secrets.ROOT / "secrets/wrapped" / registration.RECORD_NAME
REMOTE = [
    "/usr/bin/python3",
    "-I",
    "-B",
    "/usr/local/lib/trust-kms/trust_kms_service.py",
]


def recover(unwrap: str) -> bytes:
    key = secrets.recover_bundle(unwrap, record=RECORD, key_id=registration.KEY_ID)
    if len(key) != 32:
        raise ValueError("Unexpected node key length")
    return key


def enroll(talosctl: str, wrap: str, unwrap: str) -> None:
    if os.path.lexists(RECORD):
        raise FileExistsError("Node record already exists")
    report = secrets.capture_bundle(
        [
            talosctl,
            "get",
            "systeminformation",
            "--insecure",
            "--nodes",
            "10.10.0.246",
            "-o",
            "yaml",
        ],
        timeout=20,
    )
    if yaml.safe_load(report)["spec"]["uuid"].lower() != registration.NODE:
        raise ValueError("Pi UUID mismatch")
    key = os.urandom(32)
    print("Touch the YubiKey to wrap and verify the new node key.", flush=True)
    secrets.wrap_bundle(key, wrap, record=RECORD, key_id=registration.KEY_ID)
    print("Touch the YubiKey again for independent recovery.", flush=True)
    if not hmac.compare_digest(key, recover(unwrap)):
        raise ValueError("Recovered key did not match")
    print("PASS: node record created and independently recovered.")


def authorize(unwrap: str) -> None:
    status = tls_status()
    if status.get("tls_state") != "active" or status.get("kms_state") != "locked":
        raise ValueError("Expected active TLS and locked KMS")
    request_id = str(uuid4())
    print("Touch the YubiKey to recover the enrolled node key.", flush=True)
    payload = json.dumps(
        {
            "instance": status["instance"],
            "request_id": request_id,
            "key": base64.b64encode(recover(unwrap)).decode("ascii"),
        }
    ).encode()
    reply = json.loads(exchange([*REMOTE, "node-open"], payload, limit=4096))
    if (
        reply.get("instance") != status["instance"]
        or reply.get("request_id") != request_id
        or reply.get("state") != "active"
        or reply.get("authorized") != [[registration.NODE, registration.KEY_ID]]
    ):
        raise ValueError("Activation acknowledgment did not match")
    print("PASS: trust-cp1 boot window authorized.")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "action", choices=("enroll", "verify", "open", "status", "lock")
    )
    parser.add_argument("--talosctl", required=True)
    parser.add_argument("--wrap", required=True)
    parser.add_argument("--unwrap", required=True)
    args = parser.parse_args()
    try:
        if args.action in ("status", "lock"):
            print(
                exchange([*REMOTE, f"node-{args.action}"], b"", limit=4096)
                .decode()
                .strip()
            )
            return 0
        secrets.harden()
        secrets.require_private_repository(record=RECORD)
        if args.action == "enroll":
            enroll(args.talosctl, args.wrap, args.unwrap)
        elif args.action == "verify":
            print("Touch the YubiKey to verify node-key recovery.", flush=True)
            recover(args.unwrap)
            print("PASS: enrolled node key recovered.")
        else:
            authorize(args.unwrap)
    except (
        OSError,
        ValueError,
        RuntimeError,
        KeyError,
        TypeError,
        AttributeError,
        subprocess.SubprocessError,
        yaml.YAMLError,
    ):
        print(
            "Node key operation failed. Check the existing record and KMS status before retrying.",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
