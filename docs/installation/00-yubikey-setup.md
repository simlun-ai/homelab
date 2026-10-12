# 00 - YubiKey setup

**Placeholder; not yet implemented or verified.**

Configure the shared golden secret on all four YubiKeys using a trusted air-gapped laptop.

## TODO

- [ ] Prepare and pin compatible offline programming/query tools, including support for the older YubiKey Standard models.
- [ ] Document golden-key generation or retrieval through Level 1 and program the approved slot/settings on each token, preserving the memory-only handling policy.
- [ ] Implement any required verification helper; verify touch, matching responses, cross-token wrapping, and the Level 1 fallback. Record non-secret results and prepare the recovery USB clones.

References: [approved token setup](../security/yubikey-setup.md), [golden-key custody](../security/golden-key-custody.md), [secret handling](../security/security.md#secret-handling-boundary), [recovery USBs](../security/encrypted-record-storage.md#recovery-usb-clones).
