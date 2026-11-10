"""Recover, initialize or explicitly recreate wrapped staging ACME state."""

import argparse
import base64
import fcntl
import hmac
import json
import os
import shlex
import stat
import subprocess
import sys
from pathlib import Path
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parent))

import trust_kms_acme_operator as dns  # noqa: E402
import trust_talos_secrets as secrets  # noqa: E402
from homelab.record_store import require_store  # noqa: E402
from trust_kms_acme_state import LIMIT  # noqa: E402

KEY_ID = "homelab/v1/support-aux/acme/staging/r1"
FILENAME = "ups-aux-acme-staging.json"


def current_bytes(record: Path) -> bytes | None:
    if not os.path.lexists(record):
        return None
    if not stat.S_ISREG(record.lstat().st_mode):
        raise ValueError("Expected regular wrapped record")
    with record.open("rb") as stream:
        data = stream.read(2 * LIMIT + 1)
    if len(data) > 2 * LIMIT:
        raise ValueError("Oversized wrapped state")
    return data


def publish(record: Path, candidate: Path, previous: bytes | None) -> None:
    """Archive first; atomic replacement leaves the previous record on failure."""
    if current_bytes(record) != previous:
        raise ValueError("Record changed during operation")
    if previous is not None:
        archive = record.parent / "archive"
        if archive.is_symlink():
            raise ValueError("Unexpected archive link")
        archive.mkdir(mode=0o700, exist_ok=True)
        destination = archive / f"{record.stem}-{uuid4().hex}.json"
        with destination.open("xb") as stream:
            stream.write(previous)
            stream.flush()
            os.fsync(stream.fileno())
        fd = os.open(archive, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)
    with candidate.open("rb") as stream:
        os.fsync(stream.fileno())
    os.replace(candidate, record)
    fd = os.open(record.parent, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def remote(email: str, token: bytes, state: bytes | None) -> bytes:
    request = json.dumps(
        {
            "email": email,
            "token": base64.b64encode(token).decode(),
            "state": None if state is None else base64.b64encode(state).decode(),
        }
    ).encode()
    incoming = os.memfd_create("acme-request", os.MFD_CLOEXEC)
    outgoing = os.memfd_create("acme-response", os.MFD_CLOEXEC)
    try:
        os.write(incoming, request)
        os.lseek(incoming, 0, os.SEEK_SET)
        subprocess.run(
            [
                "/usr/bin/ssh",
                "-T",
                "-o",
                "BatchMode=yes",
                "-o",
                "StrictHostKeyChecking=yes",
                "-o",
                "IdentitiesOnly=yes",
                "-o",
                "ForwardAgent=no",
                "-i",
                str(dns.IDENTITY),
                dns.COORDINATOR,
                shlex.join(["sudo", "-n", "/usr/local/sbin/trust-kms-acme-state"]),
            ],
            stdin=incoming,
            stdout=outgoing,
            check=True,
            timeout=200,
        )
        if os.fstat(outgoing).st_size > LIMIT:
            raise ValueError("Oversized state")
        os.lseek(outgoing, 0, os.SEEK_SET)
        result = os.read(outgoing, LIMIT + 1)
        if not result:
            raise ValueError("Empty state")
        return result
    finally:
        os.close(incoming)
        os.close(outgoing)


def operate(mode: str, email: str, wrap: str, unwrap: str) -> None:
    store = require_store(secrets.ROOT)
    record = store / FILENAME
    # Serialize the whole read/authorize/replace transaction, including missing records.
    lock_fd = os.open(store, os.O_RDONLY | os.O_DIRECTORY)
    try:
        fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        previous = current_bytes(record)
        if mode == "init" and previous is not None:
            raise ValueError("State exists; use recover or explicit recreate")
        if mode == "recover" and previous is None:
            raise ValueError("State missing; use init or explicit recreate")
        state = None
        if mode == "recover":
            print(
                "Touch the YubiKey to recover the existing staging ACME state.",
                flush=True,
            )
            state = secrets.recover_bundle(unwrap, record=record, key_id=KEY_ID)
        dns_record = store / "ups-aux-cloudflare-dns-api.json"
        print("Touch the YubiKey to recover the Cloudflare token.", flush=True)
        token = secrets.recover_bundle(unwrap, record=dns_record, key_id=dns.KEY_ID)
        if not dns.TOKEN.fullmatch(token):
            raise ValueError()
        if mode == "recreate":
            print(
                "Explicit recreation: existing state will be archived after replacement verification."
                if previous is not None
                else "Explicit recreation: previous state unavailable; nothing to archive.",
                flush=True,
            )
        result = remote(email, token, state)
        candidate = store / f".acme-staging-pending-{uuid4().hex}.json"
        try:
            print(
                "Touch the YubiKey to wrap and verify the new staging state.",
                flush=True,
            )
            secrets.wrap_bundle(result, wrap, record=candidate, key_id=KEY_ID)
            print("Touch the YubiKey to verify independent state recovery.", flush=True)
            recovered = secrets.recover_bundle(unwrap, record=candidate, key_id=KEY_ID)
            if not hmac.compare_digest(result, recovered):
                raise ValueError("State verification failed")
            publish(record, candidate, previous)
        finally:
            candidate.unlink(missing_ok=True)
        print(
            "PASS: verified wrapped staging state published; previous ciphertext archived when present.",
            flush=True,
        )
        print(
            "Review and commit the private record and archive, then update the parent submodule pointer.",
            flush=True,
        )
    finally:
        os.close(lock_fd)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--mode", choices=("recover", "init", "recreate"), default="recover"
    )
    parser.add_argument("--email", required=True)
    parser.add_argument("--wrap", type=Path, required=True)
    parser.add_argument("--unwrap", type=Path, required=True)
    args = parser.parse_args()
    if len(args.email) > 254 or not dns.re.fullmatch(
        r"[A-Za-z0-9_.+%-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,63}", args.email
    ):
        parser.error("Supply one public ACME email")
    try:
        secrets.harden()
        os.umask(0o077)
        operate(
            args.mode,
            args.email,
            secrets.executable(args.wrap),
            secrets.executable(args.unwrap),
        )
    except (Exception, KeyboardInterrupt):
        print(
            "Staging state operation failed; private details suppressed. Existing state is not implicitly recreated. Inspect the record/archive before retrying.",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
