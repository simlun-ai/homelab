"""CI-only native recovery rehearsal with the HSM library's public fake responder."""

import argparse
import sys
from pathlib import Path
from unittest.mock import patch

from homelab_secrets import wrapping
from homelab_secrets.cli import FAKE_ROOT, fake_responder

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import trust_talos_recovery as recovery


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--talosctl", type=Path, required=True)
    parser.add_argument("--ram-root", type=Path, required=True)
    args = parser.parse_args()
    recovery.secrets.harden()
    with fake_responder() as respond:

        def wrap(plaintext: bytes, _cli: str, *, record: Path, key_id: str) -> None:
            encoded = wrapping.wrap(plaintext, key_id, FAKE_ROOT, 1, respond)
            with record.open("xb") as output:
                output.write(encoded)

        def unwrap(_cli: str, *, record: Path, key_id: str) -> bytes:
            return wrapping.unwrap(record.read_bytes(), key_id, FAKE_ROOT, respond)

        with (
            patch.object(recovery.secrets, "wrap_bundle", wrap),
            patch.object(recovery.secrets, "recover_bundle", unwrap),
        ):
            recovery.rehearse(
                recovery.secrets.executable(args.talosctl),
                "unused",
                "unused",
                args.ram_root,
            )


if __name__ == "__main__":
    try:
        main()
    except Exception:
        print("Native recovery test failed; details suppressed.", file=sys.stderr)
        raise SystemExit(1) from None
