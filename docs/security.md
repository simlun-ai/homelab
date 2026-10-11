# Security

**Status: planned design.** These decisions describe the intended setup; the YubiKeys have not been programmed or verified as part of this work.

## Document ownership

This document owns the secret-handling policy, YubiKey trust model, encryption intent, and security-related open decisions. [Backup and restore](backup-and-restore.md) owns backup operations and recovery dependencies. The [Emergency Recovery Guide](emergency-recovery-guide.md) is the single-file, non-secret guide intended for the recovery USB sticks. [Repository layout](layout.md) records where implementation and runbooks belong.

## Secret-handling boundary

Core secrets must never be committed to Git or written to workstation disk. This includes the checkout, ignored files, temporary files, credentials caches, shell history, logs, saved plans, and crash dumps. Helpers must use process memory, streams, or a verified memory-only runtime workspace; account for swap, hibernation, subprocesses, and failure paths before relying on such a workspace.

Secret references, public challenges, protocol metadata, and documentation may be committed. HMAC responses, derived secret values, golden-key material, and plaintext unseal/recovery material are secrets and must not appear in documentation, test output, or committed fixtures.

Encrypted persistence in cluster services, remote state, and backups is allowed. This includes protected Talos node state, appropriately encrypted Kubernetes secret storage, OpenBao storage, and encrypted backups. Secret delivery, backup, and restore operations must not stage sensitive contents on workstation disk.

The golden key has a separately held offline recovery record, as explicitly decided below. That record is outside the repository and workstation storage. Its physical format and custody are TBD.

## Core-secret foundation

**Decision:** All core secrets for this monorepo rely on the four YubiKeys' **OTP HMAC-SHA1 challenge-response** capability. Program all four with the same golden key and matching challenge-processing settings, so the same effective challenge bytes produce the same response on every device.

The available devices are listed in [inventory.md](inventory.md#security-keys): two YubiKey 5 NFC devices with firmware 5.2.4 and two YubiKey Standard devices with firmware 2.2.3 and 2.4.1.

Required configuration and custody:

- Use HMAC-SHA1 challenge-response for the core-secret foundation on all four devices.
- Require a physical touch before each hardware challenge-response operation.
- Keep the devices at four different locations.
- Keep one USB stick carrying the non-secret Emergency Recovery Guide with each device.
- Keep the golden key separately offline, apart from the token/guide pairs, so replacement tokens can be programmed or the same responses reproduced by a script.
- Validate existing OTP slots and select the intended slot before programming. Do not overwrite an occupied slot without explicit approval.

The four tokens are interchangeable copies of one HMAC secret. They provide location redundancy and do not establish a requirement to possess multiple tokens at once. Any OpenBao Shamir share count and threshold remain a separate decision.

Yubico documents a 20-byte HMAC secret and touch-required configuration. The configuration runbook must verify the appropriate tools, slot settings, and identical behavior on the actual older and newer devices; it must not assume that one modern CLI supports every model. See the upstream references below.

## Golden key and software recovery

The **golden key** is the secret programmed into every YubiKey's HMAC slot. It must be generated once with suitable randomness, handled only in memory during programming, and never printed, logged, exported into the checkout, or placed on the documentation USB sticks. No actual key is generated or recorded in this plan.

Keep its offline recovery record separately so it can be used to:

1. Program a replacement YubiKey with the same secret, settings, and required-touch policy.
2. Reproduce responses in software when no working token is available.
3. Recover the derived or wrapped core secrets using the same protocol metadata as the normal token path.

The software fallback must reproduce the exact effective challenge bytes and HMAC-SHA1 operation, followed by any defined derivation or unwrap steps. It has no physical touch enforcement: possession of the golden key permits software recovery. Its custody therefore protects the whole core-secret foundation.

The offline record's format, storage location, access procedure, and refresh/verification process remain TBD. Introducing its contents into a recovery workstation must still follow the memory-only handling rule.

## Challenges, derivation, and wrapped credentials

The shared HMAC foundation is decided; the per-secret protocol is still TBD. Define and version the exact challenge bytes, encoding, length/padding behavior, purpose identifiers, output encoding, and any downstream key derivation or authenticated wrapping. Preserve all non-secret parameters needed to reproduce the result in the Emergency Recovery Guide.

Use purpose-specific challenges or an explicitly documented derivation scheme for different secret roles. Sharing the golden key across devices does not require reusing one response for every role. A shared disk-unlock key remains an option, with exact formats and delivery still TBD.

| Core-secret role | Planned relationship to the HMAC foundation |
| --- | --- |
| Disk-unlock material | Derive an appropriate unlock value or unwrap existing key material; exact ZFS/Talos integration is TBD. |
| OpenBao unseal/recovery material | Protect the material produced by OpenBao initialization using HMAC-derived wrapping; share/threshold and wrapping details are TBD. |
| Cloudflare R2 restore credentials | Protect the externally issued credentials using HMAC-derived wrapping; preserve an independently accessible recovery path. |
| Talos administration/bootstrap and other monorepo core secrets | Define each required item and its derivation or wrapping in a versioned recovery manifest. The manifest format is TBD. |

Externally issued credentials and OpenBao-generated key material cannot be recreated merely by recomputing an HMAC response. Where wrapping is used, the encrypted payload must also remain recoverable independently. Locations and storage policy for those payloads are TBD; do not keep the only copy of the R2 access material inside R2 or the only Vault recovery material inside Vault.

HMAC challenge-response supplies a foundation for helper logic; it is not a native ZFS unlock integration or an OpenBao seal mechanism. OpenPGP and PKCS#11 are not part of the chosen core-secret foundation.

## Vault and runtime secret delivery

Vault must bootstrap, unlock storage, unseal OpenBao, and recover without its own OpenBao instance or another homelab cluster. Its own secrets remain manually supplied. Manual unlock and unseal fit the decided power-return policy.

Dependent clusters may consume secrets through OpenBao. Exact delivery into Talos, Kubernetes, scripts, and OpenTofu remains TBD. An external secret service or a SOPS + age fallback may still be evaluated for delivery or storage, but must preserve the chosen HMAC foundation and the workstation handling rule; encrypted payload storage in Git is not decided.

Scheduled backup jobs run inside Vault using provisioned, scoped credentials. Requiring touch when a YubiKey is queried does not require a YubiKey touch for each scheduled backup: runtime credentials can be supplied during setup and held securely server-side. Job authentication and credential lifecycle remain TBD.

## Disk encryption and OpenTofu

- **All ZFS storage:** encryption is required, including Piraeus backing storage and manually prepared pools. With native ZFS encryption, verify encryption and inheritance for datasets and zvols; pool-structure metadata is not all encrypted. Layer and provisioning sequence are TBD.
- **OS disks:** encryption is a goal. Validate Talos encryption with MD RAID1 and each hardware platform. System-volume encryption does not establish encryption of every boot partition; a static Talos STATE key stored in META must be assessed against the intended protection.
- **Manual data pools:** encryption preparation and migration must preserve the manual-storage boundary in [layout.md](layout.md#provisioning-and-storage-ownership).
- **OpenTofu:** independent state boundaries belong to each cluster. Encrypted remote state is allowed; secret-bearing local state, plans, provider output, and failure-recovery files must stay off workstation disk. Backend, locking, key delivery, and provider behavior remain TBD.
- **Bootstrap dependencies:** Vault's state backend and unlock services must be available without waiting for Vault's own protected storage or OpenBao.

## Planned YubiKey configuration runbook

Add `/runbooks/configure-yubikey-challenge-response.md`. This is a planned runbook, not an executable procedure supplied here.

It must cover:

1. Inventory all four devices, firmware, enabled interfaces, and occupied slots; record non-secret device identifiers.
2. Pin suitable programming/query tools and verify compatibility, including both YubiKey Standard devices.
3. Generate or securely load the single golden key into a memory-only session and establish its separate offline recovery record.
4. Program the chosen slots with the same HMAC secret and challenge settings, **touch required**, preserving other slot contents and approved uses.
5. Verify that no response is returned without touch, and that touching allows a response on each device.
6. Compare multiple identical public challenges across all four devices and the software fallback, keeping every response and secret comparison in memory.
7. Record slot, protocol version, challenge processing, tool versions, and any protection/access-code references without recording secret values.
8. Distribute four token/USB-guide pairs to separate locations and verify the offline golden-key recovery route.
9. Document replacement, loss, suspected compromise, rotation of the golden key and dependent material, and updating every guide.

## Remaining decisions

Slot selection and existing uses; challenge/derivation/wrapping protocol; protected-payload locations; golden-key custody; programming protection; Talos/ZFS delivery; OpenBao share policy; runtime job credentials; recovery tools; and verification/rotation procedures remain TBD. Touch-required HMAC challenge-response, matching token responses, four-location custody, and a separately held offline golden key are decided.

## Upstream references

- [Yubico HMAC-SHA1 challenge-response](https://docs.yubico.com/yesdk/users-manual/application-otp/challenge-response.html): secret format, challenge processing, and touch configuration.
- [Yubico personalization tool manual](https://developers.yubico.com/yubikey-personalization/Manuals/ykpersonalize.1.html): legacy firmware flags, HMAC mode, touch requirement, and programming behavior.
- [Talos disk encryption](https://docs.siderolabs.com/talos/v1.14/configure-your-talos-cluster/storage-and-disk-management/disk-encryption): volumes and key handling.
- [OpenZFS encryption behavior](https://openzfs.github.io/openzfs-docs/man/master/8/zfs-load-key.8.html#encryption): inheritance and metadata coverage.
- [OpenTofu state and plan encryption](https://opentofu.org/docs/language/state/encryption/): persistence and encryption considerations.
- [Kubernetes Secrets](https://kubernetes.io/docs/concepts/configuration/secret/): persistence and encryption considerations.
- [OpenBao security model](https://openbao.org/docs/internals/security/): encrypted storage and recovery material.
