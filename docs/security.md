# Security

**Planned design.** YubiKey programming, integrations, and verification are not completed.

## Secret-handling boundary

Never commit core secrets or write them to workstation disk, including ignored files, temporary files, caches, shell history, logs, saved plans, local state, and crash dumps. Use process memory, streams, or a verified memory-only workspace; account for swap, hibernation, subprocesses, and failure paths.

Public challenges, secret references, and protocol metadata may be committed. HMAC responses, derived values, golden-key material, and plaintext credentials or unseal/recovery material are secret. Keep them out of documentation, fixtures, and test output.

Encrypted persistence in cluster services, remote state, and backups is allowed, including protected Talos state, appropriately encrypted Kubernetes secret storage, and OpenBao storage. Secret and snapshot transport must not stage sensitive contents on workstation disk. The separately held offline golden-key record is outside the repository and workstation storage.

## Core-secret foundation

**Decision:** All core monorepo secrets rely on **OTP HMAC-SHA1 challenge-response** from the four [inventory YubiKeys](inventory.md#security-keys).

- Program all four with the same **golden key** and challenge-processing settings: identical effective challenge bytes must produce identical responses.
- Require physical touch for every hardware challenge-response operation.
- Keep the tokens at four separate locations, each with a USB stick carrying the non-secret [Emergency Recovery Guide](emergency-recovery-guide.md).
- Keep the golden key separately offline for replacement-token programming and software recovery.
- Inspect existing OTP slots before selecting a slot; do not overwrite an occupied slot without explicit approval.

These are interchangeable copies of one HMAC secret, providing location redundancy rather than a multi-token threshold. OpenBao's Shamir share count and threshold are separate decisions.

Yubico specifies a 20-byte HMAC secret. Verify programming/query tools and matching behavior on every actual device, including older Standard models; one modern CLI may not support all models.

## Golden key and software recovery

Generate the golden key once with suitable randomness and handle it only in memory during programming. Never print, log, or export it to the checkout or documentation USB sticks.

The offline record enables replacement tokens and software recovery. The fallback must reproduce the exact effective challenge bytes, HMAC-SHA1 operation, and subsequent derivation/unwrap steps. It cannot enforce touch: possession of the golden key gives access to the entire foundation.

Offline format, location, access, and refresh/verification procedures remain TBD. Loading the key into a recovery workstation must follow the memory-only rule.

## Challenges, derivation, and wrapped credentials

The protocol remains TBD. Version the exact challenge bytes, encoding, length/padding, purpose identifiers, output encoding, and any downstream key derivation or authenticated wrapping. Preserve public recovery parameters in the Emergency Recovery Guide.

Use purpose-specific challenges or a documented derivation scheme. Sharing a golden key across tokens does not imply one response for every role; a shared disk-unlock key remains an option.

| Secret role | Intended use of HMAC foundation |
| --- | --- |
| Disk unlock | Derive an unlock value or unwrap existing key material; ZFS/Talos integration TBD. |
| OpenBao unseal/recovery | Wrap OpenBao-generated material; share/threshold and wrapping TBD. |
| R2 restore access | Wrap externally issued credentials. |
| Talos bootstrap/administration and other core secrets | Specify derivation/wrapping in a versioned recovery manifest; format TBD. |

HMAC cannot recreate externally issued credentials or OpenBao-generated material. Wrapped secrets require both the HMAC path and a recoverable encrypted payload; independent-access requirements belong in [backup-and-restore.md](backup-and-restore.md#independent-recovery-material).

Challenge-response needs helper logic; it is not native ZFS unlock integration or an OpenBao seal mechanism. OpenPGP and PKCS#11 are outside the chosen foundation.

## Vault and runtime secret delivery

[Vault's independent bootstrap](clusters.md#vault) requires manual secret supply. Manual disk unlock and OpenBao unseal are acceptable during operator-controlled startup.

Dependent clusters may consume OpenBao secrets. Delivery into Talos, Kubernetes, scripts, and OpenTofu is TBD. An external secret service or SOPS + age may be evaluated, preserving this HMAC foundation and handling boundary; encrypted payload storage in Git is undecided.

Touch is required when querying a token, not for each scheduled backup. Runtime credentials may be provisioned at setup and held securely server-side; backup-job authentication and lifecycle belong in [backup-and-restore.md](backup-and-restore.md#openbao-online-backups).

## Disk encryption and OpenTofu

- **All ZFS storage:** require encryption, including Piraeus backing storage and manual pools. Native ZFS encryption needs dataset/zvol coverage and inheritance checks; it does not encrypt all pool metadata. Layer and provisioning sequence are TBD.
- **OS disks:** encryption is a goal. Validate Talos encryption with MD RAID1 on each platform. System-volume encryption does not establish encryption of every boot partition; assess a static STATE key stored in META against the intended protection.
- **Manual pools:** preparation and migration must preserve the [manual-storage boundary](layout.md#provisioning-and-storage-ownership).
- **OpenTofu:** encrypted remote state is allowed. Secret-bearing state, plans, provider output, and failure-recovery files must stay off workstation disk. Backend, locking, key delivery, and provider behavior are TBD; state ownership belongs in [layout.md](layout.md#common-cluster-layout).
- **Bootstrap:** Vault's state backend and unlock services must work before its protected storage or OpenBao is available.

## Planned YubiKey configuration runbook

Write `/runbooks/configure-yubikey-challenge-response.md` covering:

1. Inventory firmware, interfaces, occupied slots, and non-secret device identifiers.
2. Pin compatible programming/query tools for all four devices.
3. Generate or load the golden key in memory and establish its separate offline record.
4. Program matching slots/settings with touch required, preserving other slot contents and approved uses.
5. Verify touch enforcement on each device and compare several public challenges across all tokens and the software fallback, keeping responses and comparisons in memory.
6. Record protocol, slot, tool versions, challenge processing, and programming-protection/access-code references without secret values.
7. Distribute token/guide pairs and verify offline recovery.
8. Document replacement, loss, compromise, golden-key/dependent-material rotation, and guide updates.

## Remaining decisions

Programming protection and verification/rotation procedures remain TBD. Other open choices are marked in the relevant sections above.

## Upstream references

- [Yubico challenge-response](https://docs.yubico.com/yesdk/users-manual/application-otp/challenge-response.html).
- [Yubico personalization manual](https://developers.yubico.com/yubikey-personalization/Manuals/ykpersonalize.1.html), including legacy firmware flags.
- [Talos disk encryption](https://docs.siderolabs.com/talos/v1.14/configure-your-talos-cluster/storage-and-disk-management/disk-encryption).
- [OpenZFS encryption](https://openzfs.github.io/openzfs-docs/man/master/8/zfs-load-key.8.html#encryption).
- [OpenTofu state/plan encryption](https://opentofu.org/docs/language/state/encryption/).
- [Kubernetes Secrets](https://kubernetes.io/docs/concepts/configuration/secret/).
- [OpenBao security model](https://openbao.org/docs/internals/security/).
