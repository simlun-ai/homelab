"""Authorize a disposable coordinator Certbot rehearsal with a wrapped DNS token."""

import argparse
import re
import shlex
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import trust_talos_secrets as secrets  # noqa: E402
from homelab.record_store import StoreUnavailable, require_store  # noqa: E402

KEY_ID = "homelab/v1/support-aux/dns-api/cloudflare/r1"
COORDINATOR = "administrator@ups-aux.k8s-aux.lundmark.internal"
IDENTITY = secrets.ROOT / "support/ups/coordinator_ed25519.pub"
TOKEN = re.compile(rb"[A-Za-z0-9_-]{16,128}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--email", required=True, help="Public ACME account contact")
    parser.add_argument(
        "--record", type=Path, required=True, help="Wrapped Cloudflare token"
    )
    parser.add_argument("--unwrap", type=Path, required=True)
    args = parser.parse_args()
    email: str = args.email
    record: Path = args.record
    unwrap: Path = args.unwrap
    if not record.is_absolute():
        parser.error("Supply the absolute path to the wrapped Cloudflare record.")
    if len(email) > 254 or not re.fullmatch(
        r"[A-Za-z0-9_.+%-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,63}", email
    ):
        parser.error("Supply one public ACME contact email.")
    try:
        store = require_store(secrets.ROOT)
        if record.is_symlink() or not record.resolve().is_relative_to(store):
            parser.error(
                "The wrapped Cloudflare record must be inside secrets/wrapped."
            )
        if not record.is_file():
            print(
                "Wrapped Cloudflare record missing. See docs/installation/trust-kms-cloudflare.md.",
                file=sys.stderr,
            )
            return 1
        secrets.harden()
        print(
            "Touch the YubiKey when it flashes to recover the Cloudflare token.",
            flush=True,
        )
        token = secrets.recover_bundle(
            secrets.executable(unwrap), record=record, key_id=KEY_ID
        )
        if not TOKEN.fullmatch(token):
            raise ValueError()
        print("Streaming the token to the coordinator's staging rehearsal.", flush=True)
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
                str(IDENTITY),
                COORDINATOR,
                shlex.join(
                    ["sudo", "-n", "/usr/local/sbin/trust-kms-acme-rehearse", email]
                ),
            ],
            input=token,
            timeout=380,
            check=True,
        )
    except StoreUnavailable as exc:
        print(exc, file=sys.stderr)
        return 1
    except secrets.PreflightError as exc:
        print(f"ACME workstation preflight failed: {exc}", file=sys.stderr)
        return 1
    except (OSError, ValueError, subprocess.SubprocessError):
        print("ACME rehearsal failed. Secret details suppressed.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
