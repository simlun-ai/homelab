"""Interactive, memory-only OTP setup for the homelab's four physical tokens."""

import argparse
import getpass
import hmac
import re
import secrets
import sys
import warnings
from functools import partial

from homelab_secrets import wrapping
from homelab_secrets.runtime import harden as harden_process
from homelab_secrets.yubikey import require_no_response_without_touch, respond, token
from ykman.hid import list_otp_devices
from yubikit.yubiotp import SLOT, HmacSha1SlotConfiguration

LABELS = ("key0", "key1", "key2", "key3")
TEST_ID = "homelab/v1/setup/verification/cross-token/r1"
TEST_ROOT = "golden-1"
CHALLENGES = (b"A" * 64, bytes(range(64)), wrapping.challenge(TEST_ID))


def harden():
    harden_process(require_terminal=True)


def read_golden_key():
    with warnings.catch_warnings():
        warnings.simplefilter("error", getpass.GetPassWarning)
        first = getpass.getpass("Level 1 golden-1 (40 hex characters; hidden): ")
        second = getpass.getpass("Repeat golden-1 (hidden): ")
    if not re.fullmatch(r"[0-9a-fA-F]{40}", first) or not re.fullmatch(
        r"[0-9a-fA-F]{40}", second
    ):
        raise ValueError("Invalid golden-key input")
    first_bytes, second_bytes = bytes.fromhex(first), bytes.fromhex(second)
    if not hmac.compare_digest(first_bytes, second_bytes):
        raise ValueError("Inputs differ")
    return first_bytes


def describe(session):
    state = session.get_config_state()
    try:
        serial = session.get_serial() or None
    except Exception:
        serial = None
    print(
        f"Firmware: {session.version}; serial: {serial if serial else 'unavailable'}; "
        f"slot 1: {'occupied' if state.is_configured(SLOT.ONE) else 'empty'}; "
        f"slot 2: {'occupied' if state.is_configured(SLOT.TWO) else 'empty'}"
    )
    return serial


def confirm(label, action):
    expected = f"{action} {label} slot2"
    if action == "replace":
        print(
            "This overwrites the existing slot 2 credential. Slot 1 is preserved.",
            flush=True,
        )
        expected += " and erase existing credential"
    if input(f"Check the physical label, then type '{expected}': ") != expected:
        raise RuntimeError("Device confirmation did not match")


def verify_token(session, golden):
    if not session.get_config_state().is_configured(SLOT.TWO):
        raise RuntimeError("Slot 2 is empty")
    for challenge in CHALLENGES:
        require_no_response_without_touch(session)
        response = respond(session, challenge)
        expected = hmac.digest(golden, challenge, "sha1")
        if not hmac.compare_digest(response, expected):
            raise RuntimeError("HMAC comparison failed")
    print("PASS: touch gates and three fixed-length challenges match the Level 1 key.")


def program(session, label, golden, *, replace=False):
    if not isinstance(golden, bytes) or len(golden) != 20:
        raise ValueError("Programming requires exactly 20 golden-key bytes")
    occupied = session.get_config_state().is_configured(SLOT.TWO)
    if occupied and not replace:
        print(
            "Stop: slot 2 is occupied. Use verify or explicitly request replacement.",
            file=sys.stderr,
        )
        raise RuntimeError("Refusing an occupied slot")
    confirm(label, "replace" if occupied else "program")
    configuration = (
        HmacSha1SlotConfiguration(golden)
        .lt64(False)
        .require_touch(True)
        .allow_update(False)
    )
    session.put_configuration(SLOT.TWO, configuration)
    print("Slot 2 programmed; slot 1 was not written. Verification follows.")
    verify_token(session, golden)


def verify_set(golden):
    record = None
    payload = secrets.token_bytes(32)
    seen_serials = set()

    def software(challenge):
        return hmac.digest(golden, challenge, "sha1")

    for label in LABELS:
        input("Remove all YubiKeys, then press Enter: ")
        if list_otp_devices():
            raise RuntimeError("Remove the connected token first")
        input(f"Insert only {label}, then press Enter: ")
        with token() as session:
            serial = describe(session)
            if serial and serial in seen_serials:
                raise RuntimeError("This serial was already tested in this set")
            if serial:
                seen_serials.add(serial)
            confirm(label, "verify")
            verify_token(session, golden)
            hardware = partial(respond, session)
            if record is None:
                record = wrapping.wrap(payload, TEST_ID, TEST_ROOT, 1, hardware)
                if not hmac.compare_digest(
                    wrapping.unwrap(record, TEST_ID, TEST_ROOT, software), payload
                ):
                    raise RuntimeError("Software unwrap failed")
            if not hmac.compare_digest(
                wrapping.unwrap(record, TEST_ID, TEST_ROOT, hardware), payload
            ):
                raise RuntimeError("Cross-token unwrap failed")
            print(f"PASS: {label} unwraps the shared in-memory dummy record.")
    print(
        "PASS: all four labels and the software fallback agree. Record only the non-secret results."
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "command", choices=("inspect", "program", "verify", "verify-set")
    )
    parser.add_argument("--label", choices=LABELS)
    parser.add_argument(
        "--replace",
        action="store_true",
        help="Allow program to overwrite occupied slot 2 after an erase confirmation",
    )
    args = parser.parse_args()
    if args.command in ("program", "verify") and args.label is None:
        parser.error("--label is required")
    if args.replace and args.command != "program":
        parser.error("--replace is only valid with program")
    harden()
    if args.command == "inspect":
        with token() as session:
            describe(session)
        return
    if args.command == "verify-set":
        verify_set(read_golden_key())
        return
    with token() as session:
        describe(session)
        if (
            args.command == "program"
            and not args.replace
            and session.get_config_state().is_configured(SLOT.TWO)
        ):
            print(
                "Stop: slot 2 is occupied. Use verify or explicitly request replacement.",
                file=sys.stderr,
            )
            raise RuntimeError("Refusing an occupied slot")
        golden = read_golden_key()
        if args.command == "program":
            program(session, args.label, golden, replace=args.replace)
        else:
            confirm(args.label, "verify")
            verify_token(session, golden)
