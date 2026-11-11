"""Authorize coordinator-local wrapped staging ACME state over verified SSH."""

import argparse
import base64
import hmac
import json
import os
import shlex
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import trust_kms_acme_operator as dns  # noqa: E402
import trust_talos_secrets as secrets  # noqa: E402
from homelab.record_store import require_store  # noqa: E402
from trust_kms_acme_record import KEY_ID, current_bytes, digest  # noqa: E402
from trust_kms_acme_state import LIMIT  # noqa: E402


def exchange(command: list[str], request: bytes, *, limit: int = LIMIT) -> bytes:
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
                shlex.join(["sudo", "-n", *command]),
            ],
            stdin=incoming,
            stdout=outgoing,
            check=True,
            timeout=200,
        )
        if os.fstat(outgoing).st_size > limit:
            raise ValueError("Oversized state")
        os.lseek(outgoing, 0, os.SEEK_SET)
        result = os.read(outgoing, limit + 1)
        return result
    finally:
        os.close(incoming)
        os.close(outgoing)


def crypt(tool: str, data: bytes, *, wrap: bool) -> bytes:
    # The pinned CLIs require pipes on their secret-bearing streams. Their own
    # record/plaintext limits bound output; no filesystem paths are supplied.
    output = subprocess.run(
        [
            tool,
            "--stdin",
            "--stdout",
            "--key-id",
            KEY_ID,
            "--root-key",
            secrets.ROOT_KEY,
        ],
        input=data,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        check=True,
        timeout=180,
    ).stdout
    if not output or len(output) > (2 * LIMIT if wrap else LIMIT):
        raise ValueError("Invalid HSM output size")
    return output


def remote(email: str, token: bytes, state: bytes | None) -> bytes:
    request = json.dumps(
        {
            "email": email,
            "token": base64.b64encode(token).decode(),
            "state": None if state is None else base64.b64encode(state).decode(),
        }
    ).encode()
    result = exchange(["/usr/local/sbin/trust-kms-acme-state"], request)
    if not result:
        raise ValueError("Empty state")
    return result


def publish_remote(encoded: bytes, previous: bytes | None) -> None:
    request = json.dumps(
        {"expected": digest(previous), "record": base64.b64encode(encoded).decode()}
    ).encode()
    if (
        exchange(["/usr/local/sbin/trust-kms-acme-record", "put"], request, limit=64)
        != b"ok\n"
    ):
        raise ValueError("Publication not acknowledged")


def operate(
    mode: str, email: str, wrap: str, unwrap: str, import_record: Path | None = None
) -> None:
    # Only the DNS credential belongs to the private repository.
    store = require_store(secrets.ROOT)
    print("Fetching coordinator-local wrapped staging state.", flush=True)
    fetched = json.loads(
        exchange(["/usr/local/sbin/trust-kms-acme-record", "get"], b"", limit=3 * LIMIT)
    )["record"]
    previous = None if fetched is None else base64.b64decode(fetched, validate=True)
    if mode in ("init", "import") and previous is not None:
        raise ValueError("State exists; use recover or explicit recreate")
    if mode == "recover" and previous is None:
        raise ValueError("State missing; use init or explicit recreate")
    if mode == "import":
        if import_record is None or not import_record.is_absolute():
            raise ValueError("Supply an absolute ciphertext import path")
        encoded = current_bytes(import_record)
        if encoded is None:
            raise ValueError("Import record missing")
        print("Touch the YubiKey to verify the imported staging record.", flush=True)
        plaintext = crypt(unwrap, encoded, wrap=False)
        if json.loads(plaintext)["format"] != "trust-acme-staging-v1":
            raise ValueError("Unexpected imported state")
        publish_remote(encoded, previous)
        print(
            "PASS: verified existing ciphertext imported to the coordinator; local files unchanged.",
            flush=True,
        )
        return
    state = None
    if mode == "recover":
        print(
            "Touch the YubiKey to recover the coordinator's staging state.", flush=True
        )
        state = crypt(unwrap, previous or b"", wrap=False)
    print("Touch the YubiKey to recover the Cloudflare token.", flush=True)
    token = secrets.recover_bundle(
        unwrap, record=store / "ups-aux-cloudflare-dns-api.json", key_id=dns.KEY_ID
    )
    if not dns.TOKEN.fullmatch(token):
        raise ValueError()
    if mode == "recreate":
        print(
            "Explicit recreation: previous ciphertext will be archived on the coordinator."
            if previous is not None
            else "Explicit recreation: previous state unavailable; nothing to archive.",
            flush=True,
        )
    result = remote(email, token, state)
    print("Touch the YubiKey to wrap and verify the updated state.", flush=True)
    encoded = crypt(wrap, result, wrap=True)
    print("Touch the YubiKey to verify independent state recovery.", flush=True)
    recovered = crypt(unwrap, encoded, wrap=False)
    if not hmac.compare_digest(result, recovered):
        raise ValueError("State verification failed")
    publish_remote(encoded, previous)
    print(
        "PASS: verified ciphertext stored on the coordinator; previous ciphertext archived there when present.",
        flush=True,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--mode", choices=("recover", "init", "recreate", "import"), default="recover"
    )
    parser.add_argument(
        "--import-record",
        type=Path,
        default=os.environ.get("ACME_IMPORT_RECORD") or None,
    )
    parser.add_argument("--email", required=True)
    parser.add_argument("--wrap", type=Path, required=True)
    parser.add_argument("--unwrap", type=Path, required=True)
    args = parser.parse_args()
    if (args.mode == "import") != (args.import_record is not None):
        parser.error("Only import mode requires --import-record")
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
            args.import_record,
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
