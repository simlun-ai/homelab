# Yubico CLI fallback reference

**Reference only; not selected for installation or tested on our hardware.**

Use this guide to manually verify, debug, and sanity-check our Python implementation against Ubuntu-packaged Yubico tools. It shows the operations behind [step 00](../installation/00-yubikey-setup.md), including slot configuration, touch behavior, HMAC responses, and encryption round-trips. Examples deliberately use the **public test key** `000102030405060708090a0b0c0d0e0f10111213` and a dummy credential. Use a disposable test configuration; the real golden-key workflow stays in step 00.

## Install and inspect

Install while online. The Yubico commands come from `yubikey-personalization`; `python3-cryptography` supplies the encryption library for the later example.

```sh
sudo apt install yubikey-personalization python3-cryptography
ykpersonalize -V
ykinfo -v -1 -2
ykinfo -s
```

`ykinfo` reports firmware, slot occupancy (`1` programmed, `0` empty), and serial where available. Connect one token at a time; the CLI normally chooses the first device. Package versions and hardware compatibility still need checking on the actual Ubuntu laptop.

## Program or replace slot 1

**This overwrites slot 1; slot 2 is left alone.** The native tool uses the same command for an empty or occupied slot and asks `Commit? (y/n)`.

```sh
ykpersonalize -1 -ochal-resp -ochal-hmac -o-hmac-lt64 -ochal-btn-trig \
  -a000102030405060708090a0b0c0d0e0f10111213
```

`-ochal-resp` selects challenge-response, `-ochal-hmac` selects HMAC-SHA1, `-o-hmac-lt64` clears variable-length processing, and `-ochal-btn-trig` requires touch. Keep the mode option first among the `-o` options; it resets the defaults, including `allow-update`.

Bare `-a` instead of `-aHEX` prompts for a key; omitting it generates a random key. An existing programming access code requires separate handling. The tool prints the supplied key in its configuration preview, which is why these debugging examples use public test material.

## Query HMAC and check touch

The catalogue challenge is the SHA-256 digest represented as **64 lowercase ASCII hex characters**, with no newline:

```sh
challenge=$(printf '%s' 'homelab/v1/test/wrapping/demo/r1' | sha256sum | cut -d ' ' -f 1)
ykchalresp -1 -H "$challenge"
ykchalresp -1 -H -N "$challenge"
```

Touch for the first request; it prints the 20-byte HMAC response as 40 hex characters. For the `-N` request, do not touch: expect a touch-required/would-block error. A USB error alone does not establish touch enforcement. Add `-v` when debugging.

Repeat the first request with another token programmed with the same test key: responses must match. Do not add `-x` to these commands—it would decode the digest to 32 bytes instead of sending its 64 ASCII characters. For binary challenges, `-x` accepts 128 hex characters representing 64 bytes.

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
        ["ykchalresp", "-1", "-H", challenge], text=True
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

- [Ubuntu package and dependencies](https://packages.ubuntu.com/noble/amd64/utils/yubikey-personalization).
- Yubico manuals: [ykinfo](https://developers.yubico.com/yubikey-personalization/Manuals/ykinfo.1.html), [ykpersonalize](https://developers.yubico.com/yubikey-personalization/Manuals/ykpersonalize.1.html), [ykchalresp](https://developers.yubico.com/yubikey-personalization/Manuals/ykchalresp.1.html).
- Yubico source: [key input](https://github.com/Yubico/yubikey-personalization/blob/master/ykpers-args.c), [configuration preview](https://github.com/Yubico/yubikey-personalization/blob/master/ykpersonalize.c).
- Python cryptography: [HKDF](https://cryptography.io/en/stable/hazmat/primitives/key-derivation-functions/#hkdf), [AESGCM](https://cryptography.io/en/stable/hazmat/primitives/aead/#cryptography.hazmat.primitives.ciphers.aead.AESGCM).
