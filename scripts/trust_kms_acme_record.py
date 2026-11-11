"""Coordinator-local ciphertext storage; never handles decrypted ACME state."""

import base64
import fcntl
import hashlib
import json
import os
import stat
import sys
from pathlib import Path
from uuid import uuid4

LIMIT = 1024 * 1024
KEY_ID = "homelab/v1/support-aux/acme/staging/r1"
STORE = Path("/var/lib/trust-kms/acme-staging")
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


def digest(data: bytes | None) -> str | None:
    return None if data is None else hashlib.sha256(data).hexdigest()


def validate_record(data: bytes) -> None:
    # Structural/context guard only. AEAD and plaintext verification are performed
    # by the workstation with the YubiKey before publication, never on the Pi.
    if not data or len(data) > 2 * LIMIT:
        raise ValueError("Invalid record size")
    value = json.loads(data)
    if set(value) != {
        "format",
        "root_key",
        "key_id",
        "revision",
        "salt",
        "nonce",
        "ciphertext",
    }:
        raise ValueError("Invalid record fields")
    if (
        value["format"] != "homelab-wrap-v1"
        or value["key_id"] != KEY_ID
        or value["root_key"] != "golden-1"
    ):
        raise ValueError("Unexpected record context")
    if (
        type(value["revision"]) is not int
        or not 1 <= value["revision"] <= 9007199254740991
    ):
        raise ValueError("Invalid revision")
    for field, minimum, maximum in (
        ("salt", 32, 32),
        ("nonce", 12, 12),
        ("ciphertext", 16, LIMIT + 16),
    ):
        raw = base64.b64decode(value[field], validate=True)
        if not minimum <= len(raw) <= maximum:
            raise ValueError("Invalid encoded field")


def access(action: str, request: bytes) -> bytes:
    record = STORE / FILENAME
    # The tools play provisions this directory; never follow a substituted link.
    fd = os.open(STORE, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        info = os.fstat(fd)
        if info.st_uid != 0 or stat.S_IMODE(info.st_mode) != 0o700:
            raise ValueError("Unexpected record directory permissions")
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        previous = current_bytes(record)
        if action == "get":
            return json.dumps(
                {
                    "record": None
                    if previous is None
                    else base64.b64encode(previous).decode()
                }
            ).encode()
        if action != "put" or len(request) > 3 * LIMIT:
            raise ValueError("Invalid record operation")
        message = json.loads(request)
        if message["expected"] != digest(previous):
            raise ValueError("State changed; retry from recovery")
        replacement = base64.b64decode(message["record"], validate=True)
        validate_record(replacement)
        candidate = STORE / f".pending-{uuid4().hex}.json"
        try:
            with candidate.open("xb") as stream:
                stream.write(replacement)
            publish(record, candidate, previous)
        finally:
            candidate.unlink(missing_ok=True)
        return b"ok\n"
    finally:
        os.close(fd)


def main() -> int:
    try:
        os.umask(0o077)
        if len(sys.argv) != 2 or sys.argv[1] not in ("get", "put"):
            raise ValueError()
        request = b"" if sys.argv[1] == "get" else sys.stdin.buffer.read(3 * LIMIT + 1)
        sys.stdout.buffer.write(access(sys.argv[1], request))
        sys.stdout.buffer.flush()
    except Exception:
        print(
            "Coordinator ciphertext operation failed; current state may have changed. Inspect before retrying.",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
