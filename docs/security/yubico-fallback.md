# Yubico CLI fallback reference

**Reference only; not selected for installation or tested on our hardware.**

Use this guide to manually verify, debug, and sanity-check our Python implementation against Ubuntu-packaged Yubico tools. It shows the operations behind [step 00](../installation/00-yubikey-setup.md), including slot configuration, touch behavior, HMAC responses, and encryption round-trips. Examples deliberately use the **public test key** `000102030405060708090a0b0c0d0e0f10111213` and a dummy credential. Use a disposable test configuration; the real golden-key workflow stays in step 00.

## Install and inspect

Install while online. The commands and Python API come from `yubikey-manager`; `python3-cryptography` supplies the encryption library for the later example.

```sh
sudo apt install yubikey-manager python3-cryptography
ykman --version
ykman info
ykman otp info
```

`ykman info` reports firmware and serial where available; `ykman otp info` reports slot occupancy. Connect exactly one token at a time. Package versions, USB permissions, and compatibility with our legacy firmware still need checking on the actual Ubuntu laptop.

## Program or replace slot 2

**This overwrites slot 2; slot 1 is left alone.** Use the successor's Python API for this operation: `ykman otp chalresp --touch 2` uses variable-length processing and has no CLI option to select our fixed 64-byte mode. Its default is therefore not a substitute for the project's configuration, even if an ASCII-only test happens to pass.

Run this public-test-only example with Ubuntu's Python. It requires exactly one accessible OTP device and explicit confirmation before writing either an empty or occupied slot 2:

```sh
/usr/bin/python3 - <<'PYTHON'
from ykman.hid import list_otp_devices
from yubikit.core.otp import OtpConnection
from yubikit.yubiotp import HmacSha1SlotConfiguration, SLOT, YubiOtpSession

devices = list_otp_devices()
if len(devices) != 1:
    raise SystemExit("Connect exactly one accessible OTP-capable YubiKey")
with devices[0].open_connection(OtpConnection) as connection:
    session = YubiOtpSession(connection)
    print(f"Firmware: {session.version}; slot 2 occupied: "
          f"{session.get_config_state().is_configured(SLOT.TWO)}")
    with open("/dev/tty", "r+") as terminal:
        terminal.write("Type 'overwrite test slot2' to continue: ")
        terminal.flush()
        if terminal.readline().strip() != "overwrite test slot2":
            raise SystemExit("Cancelled")
    configuration = (HmacSha1SlotConfiguration(bytes(range(20)))
                     .lt64(False).require_touch(True).allow_update(False))
    session.put_configuration(SLOT.TWO, configuration)
PYTHON
```

`lt64(False)` selects fixed-length processing, `require_touch(True)` requires touch, and `allow_update(False)` matches the project helper. An existing programming access code requires separate handling. The example uses only the public test key; use step 00's hidden-input helper for real golden-key material.

## Query HMAC and check touch

The catalogue challenge is the SHA-256 digest represented as **64 lowercase ASCII hex characters**, with no newline. `ykman otp calculate` accepts hex-encoded bytes, so encode those ASCII characters a second time before passing them:

```sh
challenge=$(printf '%s' 'homelab/v1/test/wrapping/demo/r1' | sha256sum | cut -d ' ' -f 1)
challenge_hex=$(printf '%s' "$challenge" | od -An -v -tx1 | tr -d ' \n')
ykman otp calculate 2 "$challenge_hex"
```

Touch when prompted; the command prints the 20-byte HMAC response as 40 hex characters. Repeat with another token programmed with the same test key: responses must match. Passing `$challenge` directly would send only 32 decoded bytes and change the derived key.

There is no CLI equivalent of the old nonblocking touch check. Use the successor's API to require an explicit touch-needed status and cancel the request without touching:

```sh
/usr/bin/python3 - <<'PYTHON'
from threading import Event, Timer
from ykman.hid import list_otp_devices
from yubikit.core import TimeoutError as TokenTimeout
from yubikit.core.otp import OtpConnection, STATUS_UPNEEDED
from yubikit.yubiotp import SLOT, YubiOtpSession

devices = list_otp_devices()
if len(devices) != 1:
    raise SystemExit("Connect exactly one accessible OTP-capable YubiKey")
cancel, requested_touch = Event(), Event()
def keepalive(status):
    if status == STATUS_UPNEEDED:
        requested_touch.set()
        cancel.set()

print("Do NOT touch the test token.", flush=True)
with devices[0].open_connection(OtpConnection) as connection:
    session = YubiOtpSession(connection)
    timer = Timer(5, cancel.set)
    timer.start()
    try:
        session.calculate_hmac_sha1(SLOT.TWO, b"A" * 64, cancel, keepalive)
    except TokenTimeout:
        if not requested_touch.is_set():
            raise SystemExit("FAIL: timeout without proof that touch was required")
        print("PASS: token explicitly required touch")
    else:
        raise SystemExit("FAIL: received a response without touch")
    finally:
        timer.cancel()
        timer.join()
PYTHON
```

A timeout or USB error alone does not establish touch enforcement. For complete fixed-length and cross-token verification, run step 00's helper, which also tests a binary 64-byte challenge containing NUL.

## HMAC verification and encryption in Python

Yubico's utilities provide the token's HMAC operation. HKDF and AES-GCM run on the host. Run this example with `/usr/bin/python3` to use Ubuntu's `python3-cryptography` package. It checks the response against software HMAC using the public test key, then demonstrates the [`homelab-wrap-v1` format](security.md#challenges-derivation-and-wrapped-credentials):

```python
import base64
import hashlib
import hmac
import json
import os
import subprocess

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

key_id = "homelab/v1/test/wrapping/demo/r1"
root_key = "demo-only"
challenge = hashlib.sha256(key_id.encode("ascii")).hexdigest()
salt, nonce = os.urandom(32), os.urandom(12)
info = f"homelab-wrap-v1\0{root_key}\0{key_id}".encode("ascii")
b64 = lambda value: base64.b64encode(value).decode("ascii")

def wrapping_key():
    print("Touch the test token.")
    result = subprocess.check_output(
        ["ykman", "otp", "calculate", "2", challenge.encode("ascii").hex()], text=True
    ).strip()
    response = bytes.fromhex(result)
    assert response == hmac.digest(bytes(range(20)), challenge.encode("ascii"), "sha1")
    return HKDF(algorithm=hashes.SHA256(), length=32, salt=salt, info=info).derive(response)

header = {
    "format": "homelab-wrap-v1", "root_key": root_key, "key_id": key_id,
    "revision": 1, "salt": b64(salt), "nonce": b64(nonce),
}
aad = json.dumps(header, sort_keys=True, separators=(",", ":")).encode("ascii")
ciphertext = AESGCM(wrapping_key()).encrypt(nonce, b"demo credential", aad)
record = {**header, "ciphertext": b64(ciphertext)}

input("Keep this token or insert another with the same test key; press Enter: ")
plaintext = AESGCM(wrapping_key()).decrypt(
    nonce, base64.b64decode(record["ciphertext"]), aad
)
print(plaintext.decode("ascii"))  # demo credential
```

The HMAC response supplies HKDF's input; a fresh salt derives the 32-byte AES key. Generate fresh salt and nonce for every encryption. AES-GCM authenticates the header and protects the payload, with its tag included in `ciphertext`. Identically programmed tokens derive the same key for that record.

The header is trusted demonstration data, not an untrusted-record parser. Production use still needs the project's identifier, schema, encoding, size, and authentication checks. The example does not write a credential record to disk.

## Sources

- [Ubuntu package and dependencies](https://packages.ubuntu.com/noble/yubikey-manager).
- [YubiKey Manager OTP commands](https://docs.yubico.com/software/yubikey/tools/ykman/OTP_Commands.html).
- Yubico 5.9.2 source: [CLI configuration and challenge decoding](https://github.com/Yubico/yubikey-manager/blob/5.9.2/ykman/_cli/otp.py), [fixed-length configuration and HMAC API](https://github.com/Yubico/yubikey-manager/blob/5.9.2/yubikit/yubiotp.py), [touch requests and cancellation](https://github.com/Yubico/yubikey-manager/blob/5.9.2/yubikit/core/otp.py).
- Python cryptography: [HKDF](https://cryptography.io/en/stable/hazmat/primitives/key-derivation-functions/#hkdf), [AESGCM](https://cryptography.io/en/stable/hazmat/primitives/aead/#cryptography.hazmat.primitives.ciphers.aead.AESGCM).

