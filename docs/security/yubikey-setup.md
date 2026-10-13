# YubiKey setup

**Decision approved; programming and verification pending.**

## Configuration

Configure OTP slot 1 on all four YubiKeys with:

- The same 20-byte golden key.
- HMAC-SHA1 challenge-response.
- Fixed 64-byte challenge processing.
- Physical touch required for every response.

Slot 2 remains available. Programming access codes are deferred to
[future improvements](../future.md).

The challenge and wrapping formats are defined in
[yubikey.md](yubikey.md) and [security.md](security.md).

## Device identification

Use the existing labels `key0` through `key3`. Record each token's model,
firmware, serial number where available, and configured slot.

## Programming and verification

Install and verify dependencies while the trusted laptop is online, then
make it air-gapped before handling the golden key. Program one token at a time.
Handle the golden key and HMAC responses only in memory, following
[security.md](security.md).

Verify on every token:

- A challenge produces no response without physical touch.
- Several public 64-byte challenges produce identical responses across
  all four tokens and the software fallback.
- A dummy credential wrapped using one token can be unwrapped using
  every other token.

Keep responses and decrypted dummy payloads in memory during testing.

Record each token as configured only after programming, and verified
only after these checks pass.

## Remaining implementation work

The first helper and pinned-tooling implementation is available in
[00 - YubiKey setup](../installation/00-yubikey-setup.md). It preserves
occupied slot 1 by default; explicit replacement requires confirming its
erasure and the physical label. The Level 1 key uses a hidden local prompt.

- Test tooling preparation/installation and offline execution on the actual laptop.
- Program and verify all four devices, including the older Standard models.
- Record device identifiers and verification results; complete the recovery kits.

Golden-key custody and recovery procedures are covered separately in
[golden-key-custody.md](golden-key-custody.md) and
[recovery-procedures.md](recovery-procedures.md).
