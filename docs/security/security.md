# Security

**Planned design.** YubiKey programming, integrations, and verification are not completed.

## Secret-handling boundary

Never commit plaintext secrets, golden-key material, HMAC responses, or derived keys, or write them to workstation disk, including ignored files, temporary files, caches, shell history, logs, saved plans, local state, and crash dumps. Use process memory, streams, or a verified memory-only workspace; account for swap, hibernation, subprocesses, and failure paths.

Authenticated `homelab-wrap-v1` credential records may be committed and persisted on workstation disk, recovery USBs, and consuming hosts under the [encrypted-record storage policy](encrypted-record-storage.md). Decryption remains memory-only.

Public challenges, secret references, and protocol metadata may be committed. HMAC responses, derived values, golden-key material, and plaintext credentials or unseal/recovery material are secret. Keep them out of documentation, fixtures, and test output.

Encrypted persistence in cluster services, remote state, and backups is allowed, including protected Talos state, appropriately encrypted Kubernetes secret storage, and OpenBao storage. Transport must not stage decrypted secrets or OpenBao snapshots on workstation disk. The separately held offline golden-key record is outside the repository and workstation storage.

## Core-secret foundation

**Decision:** The **20-byte golden key** held in the four [inventory YubiKeys](../inventory.md#security-keys) is the root of trust for **all homelab secrets**, through **OTP HMAC-SHA1 challenge-response**. Secrets are derived from its responses, wrapped under response-derived keys, or protected by OpenBao, whose unseal material is wrapped under this foundation. Generated or externally issued secrets are not necessarily deterministic derivatives of the golden key.

We treat the YubiKeys as **mini hardware security modules (HSMs)** for the homelab: they hold the golden key and perform HMAC-SHA1 challenge-response on-device, with physical touch required.

- Program all four with the same **golden key** and challenge-processing settings: identical effective challenge bytes must produce identical responses.
- Require physical touch for every hardware challenge-response operation.
- Keep the tokens at four separate locations, each paired with a USB stick containing a [full repository clone](encrypted-record-storage.md#recovery-usb-clones), including wrapped records and the non-secret [Emergency Recovery Guide](../emergency-recovery-guide.md).
- Keep the golden key separately offline for replacement-token programming and software recovery.
- Use OTP slot 1 under the [approved setup](yubikey-setup.md). Neither slot is currently used on any token; inspect before programming and do not overwrite unexpected occupied slots without explicit approval.

These are interchangeable copies of one HMAC secret, providing location redundancy rather than a multi-token threshold. OpenBao uses the [approved one-share, threshold-one Shamir design](openbao-unseal.md).

Verify programming/query tools and matching behavior on every actual device, including older Standard models; one modern CLI may not support all models.

## Golden key and software recovery

Generate the golden key once with suitable randomness and handle it only in memory during programming. Never print, log, or export it to the checkout or recovery USB sticks.

The offline record enables replacement tokens and software recovery. The fallback must reproduce the exact effective challenge bytes, HMAC-SHA1 operation, and subsequent derivation/unwrap steps. It cannot enforce touch: possession of the golden key gives access to the entire foundation.

Store golden-key generations in the existing air-gapped, replicated Level 1 Password Management system under the [custody policy](golden-key-custody.md). Loading a key into a recovery workstation must follow the memory-only rule; retrieval and verification steps remain pending.

## Challenges, derivation, and wrapped credentials

**Decision:** Use HKDF-SHA-256 and AES-256-GCM for direct YubiKey wrapping, with the `homelab-wrap-v1` JSON record below. Implementation and verification are pending. The [YubiKey catalogue](yubikey.md) owns identifiers, challenge construction, consumers, and unresolved bootstrap coverage; OTP slot 1 is selected under the [approved setup](yubikey-setup.md).

### Derivation and encryption

Use the raw 20-byte HMAC-SHA1 response as HKDF input; decode any tool's hexadecimal output first. For each encryption, generate a fresh 32-byte salt and 12-byte nonce using the operating system's cryptographic RNG. Both are public. Never reuse an AES-GCM key/nonce pair.

```text
response = YubiKey(challenge(key_id))
info = ASCII("homelab-wrap-v1") || NUL || ASCII(root_key) || NUL || ASCII(key_id)
wrapping_key = HKDF-SHA-256(input=response, salt=salt, info=info, length=32)
header = record without ciphertext
aad = UTF8(JCS(header))
ciphertext = AES-256-GCM.encrypt(wrapping_key, nonce, secret_bytes, aad)
```

`||` means byte concatenation; `NUL` is one zero byte. Use full HKDF extract-and-expand. JCS is RFC 8785 JSON canonicalization. Encrypt the credential's native bytes directly and retain the full 16-byte authentication tag, appended to the ciphertext.

A fresh salt derives a new wrapping key for each encryption of a credential. The protocol label, golden-key generation, and complete identifier in `info` separate contexts. A 32-byte output does not increase the entropy of the 160-bit foundation.

### Encrypted record

Illustrative placeholders, not an actual encrypted record:

```json
{
  "format": "homelab-wrap-v1",
  "root_key": "golden-1",
  "key_id": "homelab/v1/support-vault-backup/dns-api/cloudflare/r1",
  "revision": 1,
  "salt": "<base64: 32 bytes>",
  "nonce": "<base64: 12 bytes>",
  "ciphertext": "<base64: ciphertext followed by 16-byte tag>"
}
```

The format fixes the algorithms, sizes, and encodings; no per-record algorithm negotiation. `root_key` is a public golden-key-generation label using lowercase ASCII letters, digits, and hyphens. `key_id` follows the catalogue format. `revision` is an integer from 1 through 9007199254740991. Binary fields use canonical padded standard Base64 without whitespace. Authenticate all six header fields using their JCS representation.

The caller supplies the expected `key_id` and allowed root generation independently of the record. Validate them before querying the token. Reject unknown formats, missing/extra/duplicate fields, invalid types/encodings/lengths, and authentication failures; release plaintext only after successful authentication. Set input-size limits before implementation.

### Updates, rotation, and recovery

- Updating or rewrapping a record increments `revision` and generates fresh salt and nonce. The identifier's `r1` suffix tracks the wrapping-context generation separately.
- Changing `r1` to `r2` changes the HMAC response. Every token holding the same golden key can calculate either; revoking a lost token requires replacing that shared key, rewrapping records, and rotating underlying credentials where old records could expose them.
- Authentication does not prevent replay of an older valid record. Enforcing freshness requires an independently trusted expected revision or record digest; its storage and recovery mechanism remain TBD.
- Preserve the root generation, exact identifier, encrypted record, and any trusted freshness metadata needed for each retained disk or backup. HMAC cannot reconstruct externally issued credentials or OpenBao-generated material. Independent-access requirements belong in [backup-and-restore.md](../backup-and-restore.md#independent-recovery-material).
- Keep responses and derived keys within their authorized memory-only lifetime. KMS expiry must discard both, including copies that could recreate wrapping authority.

Use Python `cryptography`'s HKDF and AESGCM APIs plus an RFC 8785-compatible serializer; dependency versions and packaging remain TBD. Before use, verify public test vectors with disposable test keys, matching behavior across all four tokens and the software fallback, malformed/tampered records, identifier substitution, rotation, and memory handling. Never use or publish real golden-key responses as test vectors.

Challenge-response needs helper logic; it is not native ZFS unlock integration or an OpenBao seal mechanism. OpenPGP and PKCS#11 are outside the chosen foundation.

## Vault and runtime secret delivery

[Vault's independent bootstrap](../clusters.md#vault) requires manual secret supply. Manual disk unlock and OpenBao unseal are acceptable during operator-controlled startup.

Application/service secrets are fetched from OpenBao; dependent clusters use External Secrets Operator where applicable. A helper on the workstation queries a YubiKey with touch, derives the wrapping key, unwraps the required unseal material, and unseals OpenBao entirely in memory. This is operator-driven unseal, not native YubiKey auto-unseal. The wrapping format is defined above; helper integration and delivery into Talos, scripts, and OpenTofu remain TBD. Wrapped credential records are stored under the [encrypted-record storage policy](encrypted-record-storage.md).

Touch is required when querying a token, not for each scheduled backup. Runtime credentials may be provisioned at setup and held securely server-side; backup-job authentication and lifecycle belong in [backup-and-restore.md](../backup-and-restore.md#openbao-online-backups).

## Disk encryption and OpenTofu

- **All ZFS storage:** require encryption, including Piraeus backing storage and manual pools. Native ZFS encryption needs dataset/zvol coverage and inheritance checks; it does not encrypt all pool metadata. Layer and provisioning sequence are TBD.
- **OS disks:** All clusters target Talos KMS-backed LUKS2 encryption for sensitive system volumes, including `STATE` and `EPHEMERAL`. Vault uses the independent [coordinator KMS](#vault-bootstrap-kms); Backup, Pi, and Metal use the [OpenBao-backed adapter](#talos-kms-adapter). This does not encrypt every boot partition. Validate volume coverage and compatibility with the assigned OS disks/MD RAID1 on each platform.
- **Manual pools:** preparation and migration must preserve the [manual-storage boundary](../layout.md#provisioning-and-storage-ownership).
- **OpenTofu:** encrypted remote state is allowed. Secret-bearing state, plans, provider output, and failure-recovery files must stay off workstation disk. Backend, locking, key delivery, and provider behavior are TBD; state ownership belongs in [layout.md](../layout.md#common-cluster-layout).
- **Bootstrap:** Vault's state backend and unlock services must work before its protected storage or OpenBao is available.

## Vault bootstrap KMS

**Decision:** Run a dedicated Python gRPC Talos KMS service on the [Vault/Backup UPS coordinator](../inventory.md#shared-infrastructure), serving Vault only. It must work without OpenBao or a Kubernetes cluster and operate independently of the workstation after [SSH authorization](coordinator-sessions.md). UPS shutdown management remains operational while KMS is locked.

- Use purpose-specific YubiKey challenges and the [v1 wrapping format](#challenges-derivation-and-wrapped-credentials) for Talos-generated unlock material. Talos retains the sealed payload in LUKS metadata; node/volume-to-identifier mapping, gRPC payload integration, and recovery copies remain TBD.
- Authorize a one-hour KMS boot window from the workstation over SSH using the operator's existing SSH key and account. The YubiKey stays in the laptop; delivery, expiry, and operator controls belong in [coordinator sessions](coordinator-sessions.md).
- Serve TLS with a publicly trusted certificate, renewed through DNS-01 on the coordinator independently of Vault's cert-manager/OpenBao. No private CA or custom Talos build is planned for KMS trust.
- Persist DNS API, TLS private-key, and ACME account/bootstrap secrets only as authenticated encrypted payloads under separate YubiKey-derived contexts. The workstation unwraps them after touch and supplies plaintext over SSH for coordinator process-memory use under the [session policy](coordinator-sessions.md). ACME integration and renewal/storage behavior require validation.
- Coordinator and Vault use the same public NTP service. Working Internet/time service is an accepted cold-start dependency; no RTC is required. Configure Vault's networking, DNS, and NTP before encrypted `STATE` loads, using boot-level settings. Establish usable time before TLS-dependent operations; endpoints and cold-boot synchronization/KMS retry tests are TBD.
- **Trusted-network boundary:** TLS authenticates the coordinator to Vault. The stock Talos KMS client does not present client credentials; request UUIDs are identifiers, not authentication. The trusted network is accepted as the client admission boundary. Make an effort to secure communication between these hosts; additional network restrictions/hardening are **TBD exactly how**. Fail closed on locked state, expiry, or unwrap errors.

Startup is **coordinator/time readiness → YubiKey-authorized KMS session → Vault system-volume unlock → manual ZFS unlock and workstation/YubiKey OpenBao unseal → transit/KMS readiness → dependent clusters**. Starting hosts remains operator-controlled.

Independent coordinator-loss recovery remains TBD in [backup-and-restore.md](../backup-and-restore.md#independent-recovery-material). The [temporary OpenBao container recovery path](../backup-and-restore.md#required-recovery-targets) bypasses the coordinator to recover OpenBao access; it does not by itself restore Vault's Talos unlock service.

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
6. Record protocol, slot, tool versions, and challenge processing. Programming access codes are deferred to [future improvements](../future.md).
7. Distribute token/guide pairs and verify offline recovery.
8. Document replacement, loss, compromise, golden-key/dependent-material rotation, and guide updates.

## Remaining decisions

Topic placeholders for the remaining decisions and implementation work:

- [Encrypted-record storage](encrypted-record-storage.md) — decision approved; implementation pending.
- [YubiKey setup](yubikey-setup.md) — decision approved; programming and verification pending.
- [Golden-key custody](golden-key-custody.md) — decision approved; backup and recovery verification pending.
- [OpenBao unseal](openbao-unseal.md) — unseal decision approved; implementation, recovery administration, and restore verification pending.
- [Credential catalogue](credential-catalogue.md) — catalogue rules approved; concrete entries and implementation pending.
- [Coordinator sessions](coordinator-sessions.md) — decision approved; implementation and verification pending.
- [Helper implementation](helper-implementation.md) — TBD.
- [Rotation and rollback](rotation-and-rollback.md) — TBD.
- [Recovery procedures](recovery-procedures.md) — TBD.

Existing decisions remain in this document and the [YubiKey catalogue](yubikey.md).

## Upstream references

- [HKDF (RFC 5869)](https://www.rfc-editor.org/rfc/rfc5869).
- [JSON canonicalization (RFC 8785)](https://www.rfc-editor.org/rfc/rfc8785).
- [Python cryptography HKDF](https://cryptography.io/en/stable/hazmat/primitives/key-derivation-functions/#hkdf) and [AESGCM](https://cryptography.io/en/stable/hazmat/primitives/aead/#cryptography.hazmat.primitives.ciphers.aead.AESGCM).
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
