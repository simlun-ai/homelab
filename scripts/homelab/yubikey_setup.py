"""Interactive, memory-only OTP setup for the homelab's four physical tokens."""

import argparse
from contextlib import contextmanager
import ctypes
import getpass
import hmac
import logging
from pathlib import Path
import re
import resource
import secrets
import sys
from threading import Event, Timer
import warnings

from ykman.hid import list_otp_devices
from yubikit.core import TimeoutError as TokenTimeout
from yubikit.core.otp import OtpConnection, STATUS_UPNEEDED
from yubikit.yubiotp import HmacSha1SlotConfiguration, SLOT, YubiOtpSession

from . import wrapping

LABELS = ("key0", "key1", "key2", "key3")
TEST_ID = "homelab/v1/setup/verification/cross-token/r1"
TEST_ROOT = "golden-1"
CHALLENGES = (b"A" * 64, bytes(range(64)), wrapping.challenge(TEST_ID))


def harden():
    logging.disable(sys.maxsize)
    if sys.platform != "linux" or not all(stream.isatty() for stream in (sys.stdin, sys.stdout, sys.stderr)):
        raise RuntimeError("Use a local Linux terminal without redirection")
    if len(Path("/proc/swaps").read_text().splitlines()) != 1:
        print("Stop: disable all swap before handling secrets.", file=sys.stderr)
        raise RuntimeError("Swap is active")
    crash_kernel = Path("/sys/kernel/kexec_crash_loaded")
    if crash_kernel.exists() and crash_kernel.read_text().strip() != "0":
        print("Stop: disable the crash kernel and reboot before handling secrets.", file=sys.stderr)
        raise RuntimeError("Crash kernel is loaded")
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    libc = ctypes.CDLL(None, use_errno=True)
    # PR_SET_DUMPABLE=0 also prevents ordinary same-user ptrace/proc memory access.
    if libc.prctl(4, 0, 0, 0, 0) != 0:
        raise RuntimeError("Cannot disable process dumping")


def read_golden_key():
    with warnings.catch_warnings():
        warnings.simplefilter("error", getpass.GetPassWarning)
        first = getpass.getpass("Level 1 golden-1 (40 hex characters; hidden): ")
        second = getpass.getpass("Repeat golden-1 (hidden): ")
    if not re.fullmatch(r"[0-9a-fA-F]{40}", first) or not re.fullmatch(r"[0-9a-fA-F]{40}", second):
        raise ValueError("Invalid golden-key input")
    first_bytes, second_bytes = bytes.fromhex(first), bytes.fromhex(second)
    if not hmac.compare_digest(first_bytes, second_bytes):
        raise ValueError("Inputs differ")
    return first_bytes


@contextmanager
def token():
    devices = list_otp_devices()
    if len(devices) != 1:
        print("Connect exactly one accessible OTP-capable YubiKey.", file=sys.stderr)
        raise RuntimeError("Ambiguous or unavailable device")
    with devices[0].open_connection(OtpConnection) as connection:
        session = YubiOtpSession(connection)
        if session.version < (2, 2, 0):
            raise RuntimeError("Firmware lacks HMAC challenge-response")
        yield session


def describe(session):
    state = session.get_config_state()
    try:
        serial = session.get_serial() or None
    except Exception:
        serial = None
    print(f"Firmware: {session.version}; serial: {serial if serial else 'unavailable'}; "
          f"slot 1: {'occupied' if state.is_configured(SLOT.ONE) else 'empty'}; "
          f"slot 2: {'occupied' if state.is_configured(SLOT.TWO) else 'empty'}")
    return serial


def confirm(label, action):
    expected = f"{action} {label} slot1"
    if input(f"Check the physical label, then type '{expected}': ") != expected:
        raise RuntimeError("Device confirmation did not match")


def require_no_response_without_touch(session):
    print("Do NOT touch: checking that a request waits for physical touch.", flush=True)
    cancel, requested_touch = Event(), Event()

    def keepalive(status):
        if status == STATUS_UPNEEDED:
            requested_touch.set()
            cancel.set()

    timer = Timer(5, cancel.set)
    timer.start()
    try:
        session.calculate_hmac_sha1(SLOT.ONE, CHALLENGES[0], cancel, keepalive)
    except TokenTimeout:
        if not requested_touch.is_set():
            raise RuntimeError("Timeout without proof that touch was required") from None
    else:
        raise RuntimeError("Received a response without the required touch gate")
    finally:
        timer.cancel()
        timer.join()


def respond(session, challenge):
    if len(challenge) != 64:
        raise ValueError("Only fixed 64-byte challenges are allowed")
    print("Touch the connected YubiKey when it flashes.", flush=True)
    cancel = Event()
    timer = Timer(20, cancel.set)
    timer.start()
    try:
        response = session.calculate_hmac_sha1(SLOT.ONE, challenge, cancel)
    finally:
        timer.cancel()
        timer.join()
    if len(response) != 20:
        raise RuntimeError("Invalid response size")
    return response


def verify_token(session, golden):
    if not session.get_config_state().is_configured(SLOT.ONE):
        raise RuntimeError("Slot 1 is empty")
    for challenge in CHALLENGES:
        require_no_response_without_touch(session)
        response = respond(session, challenge)
        expected = hmac.digest(golden, challenge, "sha1")
        if not hmac.compare_digest(response, expected):
            raise RuntimeError("HMAC comparison failed")
    print("PASS: touch gates and three fixed-length challenges match the Level 1 key.")


def program(session, label, golden):
    if not isinstance(golden, bytes) or len(golden) != 20:
        raise ValueError("Programming requires exactly 20 golden-key bytes")
    if session.get_config_state().is_configured(SLOT.ONE):
        print("Stop: slot 1 is occupied. Use verify; this helper cannot overwrite it.", file=sys.stderr)
        raise RuntimeError("Refusing an occupied slot")
    confirm(label, "program")
    configuration = HmacSha1SlotConfiguration(golden).lt64(False).require_touch(True).allow_update(False)
    session.put_configuration(SLOT.ONE, configuration)
    print("Slot 1 programmed; slot 2 was not written. Verification follows.")
    verify_token(session, golden)


def verify_set(golden):
    record = None
    payload = secrets.token_bytes(32)
    seen_serials = set()
    software = lambda challenge: hmac.digest(golden, challenge, "sha1")
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
            hardware = lambda challenge: respond(session, challenge)
            if record is None:
                record = wrapping.wrap(payload, TEST_ID, TEST_ROOT, 1, hardware)
                if not hmac.compare_digest(wrapping.unwrap(record, TEST_ID, TEST_ROOT, software), payload):
                    raise RuntimeError("Software unwrap failed")
            if not hmac.compare_digest(wrapping.unwrap(record, TEST_ID, TEST_ROOT, hardware), payload):
                raise RuntimeError("Cross-token unwrap failed")
            print(f"PASS: {label} unwraps the shared in-memory dummy record.")
    print("PASS: all four labels and the software fallback agree. Record only the non-secret results.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("inspect", "program", "verify", "verify-set"))
    parser.add_argument("--label", choices=LABELS)
    args = parser.parse_args()
    if args.command in ("program", "verify") and args.label is None:
        parser.error("--label is required")
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
        if args.command == "program" and session.get_config_state().is_configured(SLOT.ONE):
            print("Stop: slot 1 is occupied. Use verify; do not reprogram it.", file=sys.stderr)
            raise RuntimeError("Refusing an occupied slot")
        golden = read_golden_key()
        if args.command == "program":
            program(session, args.label, golden)
        else:
            confirm(args.label, "verify")
            verify_token(session, golden)
