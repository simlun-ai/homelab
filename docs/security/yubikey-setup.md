# YubiKey setup

**Decision approved; programming and verification pending.**

## Configuration

Configure OTP slot 2 on all four YubiKeys with:

- The same 20-byte golden key.
- HMAC-SHA1 challenge-response.
- Fixed 64-byte challenge processing.
- Physical touch required for every response.

Slot 1 remains available. Programming access codes are deferred to
[future improvements](../future.md).

The challenge and wrapping formats are defined in
[yubikey.md](yubikey.md) and [security.md](security.md).

## Device identification

Use the existing labels `key0` through `key3`. Record each token's model,
firmware, serial number where available, and configured slot.

## Programming and verification

Use the offline level1vault live OS. Install homelab-hsm from its transported
wheel bundle and program one token at a time using its Python CLI.
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
occupied slot 2 by default; explicit replacement requires confirming its
erasure and the physical label. The Level 1 key arrives through a pipe from pass; confirmations use /dev/tty.

- Test tooling preparation/installation and offline execution in the actual live OS.
- Program and verify all four devices, including the older Standard models.
- Record device identifiers and verification results.

Golden-key custody and recovery procedures are covered separately in
[golden-key-custody.md](golden-key-custody.md) and
[recovery-procedures.md](recovery-procedures.md).

