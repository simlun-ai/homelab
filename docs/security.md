# Security

**Planned design.** YubiKey programming, integrations, and verification are not completed.

## Secret-handling boundary

Never commit secrets or write them to workstation disk, including ignored files, temporary files, caches, shell history, logs, saved plans, local state, and crash dumps. Use process memory, streams, or a verified memory-only workspace; account for swap, hibernation, subprocesses, and failure paths.

Public challenges, secret references, and protocol metadata may be committed. HMAC responses, derived values, golden-key material, and plaintext credentials or unseal/recovery material are secret. Keep them out of documentation, fixtures, and test output.

Encrypted persistence in cluster services, remote state, and backups is allowed, including protected Talos state, appropriately encrypted Kubernetes secret storage, and OpenBao storage. Secret and snapshot transport must not stage sensitive contents on workstation disk. The separately held offline golden-key record is outside the repository and workstation storage.

## Core-secret foundation

**Decision:** The **20-byte golden key** held in the four [inventory YubiKeys](inventory.md#security-keys) is the root of trust for **all homelab secrets**, through **OTP HMAC-SHA1 challenge-response**. Secrets are derived from its responses, wrapped under response-derived keys, or protected by OpenBao, whose unseal material is wrapped under this foundation. Generated or externally issued secrets are not necessarily deterministic derivatives of the golden key.

We treat the YubiKeys as **mini hardware security modules (HSMs)** for the homelab: they hold the golden key and perform HMAC-SHA1 challenge-response on-device, with physical touch required.

- Program all four with the same **golden key** and challenge-processing settings: identical effective challenge bytes must produce identical responses.
- Require physical touch for every hardware challenge-response operation.
- Keep the tokens at four separate locations, each with a USB stick carrying the non-secret [Emergency Recovery Guide](emergency-recovery-guide.md).
- Keep the golden key separately offline for replacement-token programming and software recovery.
- Inspect existing OTP slots before selecting a slot; do not overwrite an occupied slot without explicit approval.

These are interchangeable copies of one HMAC secret, providing location redundancy rather than a multi-token threshold. OpenBao's Shamir share count and threshold are separate decisions.

Verify programming/query tools and matching behavior on every actual device, including older Standard models; one modern CLI may not support all models.

## Golden key and software recovery

Generate the golden key once with suitable randomness and handle it only in memory during programming. Never print, log, or export it to the checkout or documentation USB sticks.

The offline record enables replacement tokens and software recovery. The fallback must reproduce the exact effective challenge bytes, HMAC-SHA1 operation, and subsequent derivation/unwrap steps. It cannot enforce touch: possession of the golden key gives access to the entire foundation.

Offline format, location, access, and refresh/verification procedures remain TBD. Loading the key into a recovery workstation must follow the memory-only rule.

## Challenges, derivation, and wrapped credentials

The protocol remains TBD. Version the exact challenge bytes, encoding, length/padding, purpose identifiers, output encoding, and any downstream key derivation or authenticated wrapping. Preserve public recovery parameters in the Emergency Recovery Guide.

Use purpose-specific challenges and a documented key derivation scheme to turn HMAC responses into suitable wrapping keys. Helpers use authenticated encryption to wrap/unwrap secret payloads; HMAC-SHA1 itself is not an encryption algorithm. Exact algorithms and payload format remain TBD.

| Secret role | Intended use of HMAC foundation |
| --- | --- |
| Manual ZFS data-pool unlock | Wrap/unwrap encryption keys using HMAC-response-derived keys; helper integration TBD. |
| OpenBao unseal/recovery | Workstation helper unwraps OpenBao-generated unseal material using a YubiKey response, then submits it to OpenBao; share/threshold TBD. |
| Vault Talos system-volume unlock | Dedicated coordinator KMS wraps/unwraps Talos-generated unlock material using the YubiKey foundation; see [Vault bootstrap KMS](#vault-bootstrap-kms). |
| Coordinator KMS TLS and DNS-01 credentials | Wrap private keys and the DNS API credential; decrypt only into coordinator memory after touch. |
| Dependent Talos system-volume unlock | Talos KMS adapter delegates sealing/unsealing to OpenBao transit; see below. |
| Application/service secrets | Fetch from OpenBao after unseal, rather than querying a YubiKey for each secret. |
| R2 restore access | Wrap externally issued credentials. |
| Talos bootstrap/administration and other core secrets | Specify derivation/wrapping in a versioned recovery manifest; format TBD. |

HMAC cannot recreate externally issued credentials or OpenBao-generated material. Wrapped secrets require both the HMAC path and a recoverable encrypted payload; independent-access requirements belong in [backup-and-restore.md](backup-and-restore.md#independent-recovery-material).

Challenge-response needs helper logic; it is not native ZFS unlock integration or an OpenBao seal mechanism. OpenPGP and PKCS#11 are outside the chosen foundation.

## Vault and runtime secret delivery

[Vault's independent bootstrap](clusters.md#vault) requires manual secret supply. Manual disk unlock and OpenBao unseal are acceptable during operator-controlled startup.

Application/service secrets are fetched from OpenBao; dependent clusters use External Secrets Operator where applicable. A helper on the workstation queries a YubiKey with touch, derives the wrapping key, unwraps the required unseal material, and unseals OpenBao entirely in memory. This is operator-driven unseal, not native YubiKey auto-unseal. Exact helper protocol and delivery into Talos, scripts, and OpenTofu remain TBD; encrypted payload storage in Git is undecided.

Touch is required when querying a token, not for each scheduled backup. Runtime credentials may be provisioned at setup and held securely server-side; backup-job authentication and lifecycle belong in [backup-and-restore.md](backup-and-restore.md#openbao-online-backups).

## Disk encryption and OpenTofu

- **All ZFS storage:** require encryption, including Piraeus backing storage and manual pools. Native ZFS encryption needs dataset/zvol coverage and inheritance checks; it does not encrypt all pool metadata. Layer and provisioning sequence are TBD.
- **OS disks:** All clusters target Talos KMS-backed LUKS2 encryption for sensitive system volumes, including `STATE` and `EPHEMERAL`. Vault uses the independent [coordinator KMS](#vault-bootstrap-kms); Backup, Pi, and Metal use the [OpenBao-backed adapter](#talos-kms-adapter). This does not encrypt every boot partition. Validate volume coverage and compatibility with the assigned OS disks/MD RAID1 on each platform.
- **Manual pools:** preparation and migration must preserve the [manual-storage boundary](layout.md#provisioning-and-storage-ownership).
- **OpenTofu:** encrypted remote state is allowed. Secret-bearing state, plans, provider output, and failure-recovery files must stay off workstation disk. Backend, locking, key delivery, and provider behavior are TBD; state ownership belongs in [layout.md](layout.md#common-cluster-layout).
- **Bootstrap:** Vault's state backend and unlock services must work before its protected storage or OpenBao is available.

## Vault bootstrap KMS

**Decision:** Run a dedicated Python gRPC Talos KMS service on the [Vault/Backup UPS coordinator](inventory.md#shared-infrastructure), serving Vault only. It must work without OpenBao, a Kubernetes cluster, or a workstation. UPS shutdown management remains operational while KMS is locked.

- Use purpose-specific YubiKey challenge-response and a KDF/authenticated wrapping scheme to seal/unseal Talos-generated unlock material. Talos retains the sealed payload in LUKS metadata; exact protocol, payload format, and recovery copies remain TBD.
- A touched YubiKey enables a short boot session covering system-volume unlock and retries. Keep the KMS wrapping key only in memory and discard it when the window expires; already unlocked volumes continue running. Subsequent unlock requires another authorized session; duration and operator controls are TBD.
- Serve TLS with a publicly trusted certificate, renewed through DNS-01 on the coordinator independently of Vault's cert-manager/OpenBao. No private CA or custom Talos build is planned for KMS trust.
- Persist the DNS API credential and TLS private key only as authenticated encrypted payloads under separate YubiKey-derived wrapping contexts. After touch, retain plaintext only in coordinator process memory for its running lifetime, independently of the shorter KMS window. Restart/power loss requires touch again. Apply the same protection to ACME account/bootstrap secrets; prevent credential files, swap, dumps, and persistent secret logs. ACME integration and renewal/storage behavior require validation.
- Coordinator and Vault use the same public NTP service. Working Internet/time service is an accepted cold-start dependency; no RTC is required. Configure Vault's networking, DNS, and NTP before encrypted `STATE` loads, using boot-level settings. Establish usable time before TLS-dependent operations; endpoints and cold-boot synchronization/KMS retry tests are TBD.
- **Trusted-network boundary:** TLS authenticates the coordinator to Vault. The stock Talos KMS client does not present client credentials; request UUIDs are identifiers, not authentication. The trusted network is accepted as the client admission boundary. Make an effort to secure communication between these hosts; additional network restrictions/hardening are **TBD exactly how**. Fail closed on locked state, expiry, or unwrap errors.

Startup is **coordinator/time readiness → YubiKey-authorized KMS session → Vault system-volume unlock → manual ZFS unlock and workstation/YubiKey OpenBao unseal → transit/KMS readiness → dependent clusters**. Starting hosts remains operator-controlled.

Independent coordinator-loss recovery remains TBD in [backup-and-restore.md](backup-and-restore.md#independent-recovery-material). The [temporary OpenBao container recovery path](backup-and-restore.md#required-recovery-targets) bypasses the coordinator to recover OpenBao access; it does not by itself restore Vault's Talos unlock service.

## Talos KMS adapter

**Decision:** Implement a small Python service using the [Talos KMS protocol](https://github.com/siderolabs/kms-client/blob/main/api/kms/kms.proto), with OpenBao's transit engine performing the cryptography. The protocol is **gRPC**, with `Seal` and `Unseal` RPCs, not a plain HTTP/JSON web API.

- `Seal`: pass the Talos-generated unlock material to transit `encrypt`; return its ciphertext in the protocol's response bytes.
- `Unseal`: pass the stored ciphertext to transit `decrypt`; return the decoded unlock material. Preserve a versioned payload format and the necessary transit key versions.
- Use TLS and scoped transit permissions. Node UUIDs in requests are identifiers, not proof of identity; client authorization compatible with Talos remains TBD. Fail closed on backend or decryption errors.

Planned placement is Vault, beside OpenBao, so the adapter is available before dependent nodes boot. Its credentials and TLS configuration must bootstrap without those nodes. Startup follows the [coordinator-first sequence](#vault-bootstrap-kms), then **OpenBao unseal → transit/KMS readiness → Backup, Pi, and Metal**. Nodes need KMS access again when unlocking after a reboot; touch is required for OpenBao unseal, not each KMS request.

For encrypted `STATE`, networking must work before the machine configuration can be read, and custom CA certificates stored in `STATE` cannot establish KMS trust. Settle early-boot addressing/DNS and a Talos-supported TLS trust path before rollout. Adapter packaging, endpoint, authentication, timeouts, key mapping/rotation, and restore tests remain TBD; do not copy the reference test server's random-data fallback behavior.

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
- [Talos KMS reference implementation](https://github.com/siderolabs/kms-client).
- [Talos v1.14.2 KMS client and TLS behavior](https://github.com/siderolabs/talos/blob/v1.14.2/internal/pkg/encryption/keys/kms.go).
- [Talos preboot networking/DNS/NTP kernel parameters](https://github.com/siderolabs/talos/blob/v1.14.2/website/content/v1.14/reference/kernel.md).
- [OpenBao transit API](https://openbao.org/docs/api/secret/transit/).
