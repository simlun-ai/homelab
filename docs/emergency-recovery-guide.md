# Emergency Recovery Guide

**Homelab Recovery Kit — non-secret, single-file draft.** For recovering Vault and OpenBao when the original hardware or services are unavailable.

Exact commands and recovery metadata must be completed and tested before use. Essential instructions are included here because the USB copy must work without other local documents.

## Revision and recovery metadata

All entries must be non-secret.

| Field | Value |
| --- | --- |
| Guide revision / repository commit; last verified restore | TBD. |
| Core-secret protocol version and YubiKey HMAC slot | `homelab-wrap-v1`; OTP slot 1 selected, fixed 64-byte challenges, touch required. Programming/verification pending. |
| Effective challenge bytes, encoding, purpose identifiers, length/padding | V1 construction below; exact recovery identifiers and device verification TBD. |
| Derivation/wrapping algorithms, output encoding, public parameters | HKDF-SHA-256 + AES-256-GCM; JSON/JCS and padded Base64 as specified below. |
| Snapshot OpenBao version, ARM64 Pi and workstation recovery images/tools; independent acquisition locations | TBD. |
| Container memory mounts, required RAM, runtime/swap/logging checks; tested Pi/container procedures | TBD. |
| Tool and backup integrity/checksum verification | TBD. |
| R2 account, endpoint, bucket, object convention; snapshot selection | TBD. |
| Additional backup-encryption details | TBD. |
| Independent encrypted-payload references | Wrapped records and public manifest under `secrets/wrapped/` in the USB's full repository clone. OpenBao Shamir seal: one share, threshold one; identifier `homelab/v1/vault/openbao-unseal/share-1/r1`. Exact filenames and recovery administration credential TBD. Accessible without Vault, GitHub, or existing R2 credentials. |
| Golden-key retrieval procedure reference | Level 1 Password Management system; exact retrieval steps outside this repository. Never record the key here. |
| Vault coordinator KMS endpoint, public TLS/DNS-01, preboot DNS/NTP, session controls | TBD; include service acquisition, independent wrapped-payload references, and coordinator rebuild instructions. |
| KMS adapter endpoint, TLS trust, early-boot networking, transit key mapping/versions | TBD; include adapter acquisition and independent bootstrap-payload references. |
| Per-device power-return limitations and manual startup procedure | TBD. |

## Required access and operating rules

Use one working YubiKey and its paired recovery USB containing a full, non-shallow homelab repository clone, including this guide and the wrapped recovery records, plus a recovery workstation with the specified tools. All homelab secrets are rooted in the 20-byte golden key through derivation, wrapping, or OpenBao protected by wrapped unseal material. All four tokens share the golden key and HMAC-SHA1 settings and are kept at separate locations; identical effective challenges produce identical responses. One token suffices; if none works, obtain the separately held offline golden key.

- The USB contains the full repository clone and authenticated wrapped records. Never include golden-key material, HMAC responses, derived keys, plaintext credentials/unseal shares/private keys, decrypted secret-bearing configuration, or embedded Git access tokens.
- Wrapped `homelab-wrap-v1` records may be stored in Git, on workstation disk, on recovery USBs, and on consuming hosts. Never write decrypted secrets, golden-key material, HMAC responses, derived keys, or OpenBao snapshots to workstation disk, including temporary files, caches, shell history, logs, state, or saved plans. Verify memory-only handling, including swap, hibernation, subprocesses, and failure paths.
- Hardware challenge-response requires touch; the golden-key software fallback cannot enforce it.
- Preserve manual non-Piraeus ZFS pools during node installation or repair; do not wipe or initialize them.
- Vault recovery must work without its failed OpenBao instance or another cluster. Its system-volume KMS runs independently on the Vault/Backup coordinator; public NTP/Internet is an accepted cold-start dependency. DNS, TLS, and ACME payloads are encrypted at rest. Keep the YubiKey in the workstation laptop and use the operator's existing SSH key/account with verified coordinator host identity to deliver authorized material through SSH standard input and a restricted local Unix socket. Send plaintext runtime credentials and unwrapped random 32-byte KMS keys for explicitly authorized Vault nodes, never the golden key or raw HMAC responses; keep secrets out of arguments, files, and logs. KMS authority lasts one hour from successful activation, measured by the coordinator's monotonic clock; requests do not extend it. Expiry or explicit lock discards KMS authority. DNS/TLS/ACME secrets last for the coordinator process lifetime. SSH may disconnect; coordinator restart requires fresh authorization. SSH access must work without Vault/OpenBao. The node KMS key is itself YubiKey-wrapped in a `homelab-wrap-v1` record stored in the repository, USB clones, and coordinator storage. It protects Talos unlock secrets in a distinct `homelab-kms-v1` envelope stored in disk LUKS metadata. Seal creates that envelope during disk preparation; Unseal decrypts it on later boots. Recover the existing node KMS key rather than generating a replacement; retain older generations required by disks. Exact delivery commands and the inner envelope specification remain pending. Communication uses TLS on a trusted network; additional host-to-host network hardening remains TBD.
- After UPS-triggered shutdown, power machines on manually, one at a time, with Vault services ready before dependent clusters. Disable automatic power-return startup and wake sources where supported; account for device limitations.

## Recovery repository and local records

Use the USB's checked-out repository and local Git history to find `secrets/wrapped/`, its public identifier-to-file manifest, this guide, and helper source without GitHub or OpenBao. Snapshot backups remain in R2; required binaries/dependencies still need the specified acquisition procedure.

Refresh all four full clones after recovery-critical changes, record each clone's commit, and verify integrity and required records. Exact refresh and verification commands remain TBD. The coordinator uses its own locally deployed wrapped records at startup; planned Ansible provisioning copies ciphertext without decrypting it. Implementation remains pending.

## Recover core-secret access

1. Select the recorded HMAC slot and protocol version. Obtain the specified helper and verify its integrity.
2. Load the exact public challenge and derivation/wrapping parameters.
3. Query the token and touch it; keep responses and subsequent secret values in memory.
4. Derive or unwrap R2 access, backup-decryption, OpenBao unseal/recovery, and node bootstrap/unlock material using the independent payloads. HMAC alone cannot recreate externally issued credentials or OpenBao-generated material.

If a token fails, obtain another token/guide pair. Never guess encoding or overwrite an occupied slot.

## V1 wrapping protocol

**Selected design; helper and device verification pending.** This embedded specification must remain synchronized with the maintained security policy.

Records have exactly seven fields: `format` (`homelab-wrap-v1`), `root_key` (public generation label, initially `golden-1`), `key_id`, `revision`, `salt`, `nonce`, and `ciphertext`. Root labels use lowercase ASCII letters, digits, and hyphens. Identifiers follow `homelab/v1/<scope>/<purpose>/<resource>/r<generation>`, with lowercase ASCII letters, digits, hyphens, and slash-separated nonempty segments; no whitespace or trailing newline. Exact resource identifiers remain to be recorded.

`revision` is an integer from 1 through 9007199254740991. Salt, nonce, and ciphertext use canonical padded standard Base64 without whitespace. Decode a 32-byte salt, a 12-byte nonce, and ciphertext ending in the full 16-byte GCM tag.

```text
challenge = ASCII(lowercase_hex(SHA256(ASCII(key_id))))
response = HMAC-SHA1(golden_key, challenge)
info = ASCII("homelab-wrap-v1") || NUL || ASCII(root_key) || NUL || ASCII(key_id)
wrapping_key = HKDF-SHA-256(input=response, salt=salt, info=info, length=32)
header = record without ciphertext
aad = UTF8(JCS(header))
secret_bytes = AES-256-GCM.decrypt(wrapping_key, nonce, ciphertext, aad)
```

The token computes the HMAC with touch; software fallback performs the identical operation. The challenge is exactly 64 bytes with fixed-length processing. Use the raw 20-byte response, full HKDF extract-and-expand, one zero byte for each `NUL`, byte concatenation for `||`, and RFC 8785 canonicalization for `JCS`.

Obtain the expected identifier and allowed root generation independently; compare them before querying the token. Reject unknown formats, missing/extra/duplicate fields, invalid types/encodings/lengths, and failed authentication. Release plaintext only after authentication succeeds. Helper size limits remain TBD. Strong rollback enforcement is deferred; initial tooling does not independently enforce record freshness.

Every encryption uses fresh cryptographic random salt and nonce; never reuse a key/nonce pair. Updates/rewrapping increment the record revision. An old authentic record can still decrypt. Track revisions and explicitly select records for recovery; strong rollback enforcement through independently trusted revision or digest state is deferred. Retain the generations and records needed by the selected disk or snapshot. Changing the identifier's wrapping generation cannot revoke a token sharing the golden key.

The helper uses Python `cryptography` HKDF/AESGCM and an RFC 8785-compatible serializer; pinned versions and acquisition commands remain TBD. KMS session expiry discards the node KMS keys, derived payload keys, and secret copies, separately from the coordinator's longer-lived DNS/TLS/ACME material. Raw YubiKey responses and wrapping keys remain only briefly on the workstation.

## Golden-key fallback and replacement token

Retrieve the required golden-key generation from the air-gapped, replicated Level 1 Password Management system. Each entry holds the key as exactly 40 hexadecimal characters, preserving leading zeros, and its generation label matching the record's `root_key`. Level 1's internal procedures and locations are outside this guide. Load the key into the verified memory-only session without logging. The helper must compute HMAC-SHA1 over identical effective challenge bytes, then apply the same derivation/unwrap steps.

Replacement programming must use the same key/settings with **touch required**, preserve occupied slots unless explicitly approved, verify behavior, record the non-secret device identity, and return a current token/guide pair to its location. Exact helper acquisition, programming commands, and verification steps remain TBD.

## Restore Vault and OpenBao

OpenBao backups are online Raft snapshots uploaded by a job inside Vault to Cloudflare R2. Required targets are a full Vault rebuild on a replacement Raspberry Pi 4 and temporary OpenBao recovery in a Linux container on a trusted workstation. Both require documented, tested procedures; neither is verified yet. Start with the OpenBao version recorded for the snapshot and independently obtainable configuration/tools.

1. Recover R2 access and any wrapped/decryption material.
2. Select a snapshot and validate its recorded identity/integrity; do not stage it on workstation disk.
3. Choose a target. **Full Pi 4 rebuild:** recover/start the coordinator, establish time/DNS/public KMS TLS, authorize the one-hour KMS boot window over SSH using a YubiKey in the workstation, and bootstrap/unlock Talos while preserving manual ZFS storage. **Temporary container:** run a normal single-node Raft-backed OpenBao server with data, snapshot input, secret-bearing configuration, and temporary files on verified memory-backed mounts. It needs no Talos/coordinator. Prevent disk writes through writable layers, host volumes, swap/hibernation, dumps, and engine metadata/logs; account for VM-backed runtimes. Exact commands and resource sizing remain TBD.
4. Restore the snapshot with its corresponding seal/unseal material. Use the workstation helper and a touched YubiKey (or the software fallback) to unwrap and submit the required unseal material in memory. **Exact initialization, restore, and unseal ordering is TBD and must be validated; new-instance material may not unlock an older snapshot.**
5. Verify recovery administration access, expected secrets/authentication/policies, and transit decryption of previously sealed test material. Keep drills isolated from production integrations. For full Pi recovery, also verify certificate distribution and resumed encrypted snapshot uploads. For a temporary container, preserve any required changes in a fresh encrypted snapshot through compliant transfer before teardown; memory-backed state is lost when the container ends.
6. For full Pi recovery, restore/verify the Python gRPC KMS adapter and required OpenBao transit key versions. Backup, Pi, and Metal need this service to unlock Talos system volumes; Vault must unlock independently. An older snapshot may lack transit keys required by newer disks. Verify early-boot network access and TLS trust before starting nodes.
7. After foundation services are restored and verified, start dependent clusters manually, one machine at a time, checking KMS unlock, dependencies, and storage. A temporary OpenBao container alone does not restore the cluster's KMS endpoints or other services.

## Complete before distributing a usable kit

Test token failure and the Level 1 fallback, coordinator rebuild with independent SSH access, replacement-Pi restore, RAM-backed container restore, and recovery-kit refresh. Record the repository commit, snapshot identity, key generations, tool versions, result, and recovery time without secrets. A procedure is verified only after successful testing on its required target.

Fill every recovery-critical field and embed exact acquisition, operating, and failure-handling commands in this file. Test touch enforcement and matching responses across all tokens and the software fallback without recording secret output. Prove both replacement-Pi and workstation-container R2 restores with a separately held token/guide pair and with the golden-key fallback, without the original Vault/coordinator or workstation-disk plaintext secrets. Refresh and verify every USB repository clone after recovery-critical changes.

## Maintenance references

These references do not replace embedded emergency instructions.

- Policies: `docs/security/security.md` and `docs/backup-and-restore.md`.
- Credential catalogue and v1 challenge format: `docs/security/yubikey.md`; wrapping specification: `docs/security/security.md`. Keep the embedded protocol synchronized and add exact recovery-critical identifiers before distributing the guide.
- Installation plan and runbooks: `docs/installation/README.md`, `docs/installation/00-yubikey-setup.md`, `docs/installation/01-main-coordinator.md`, `docs/installation/02-vault.md`. Step 00 has an initial helper implementation; physical verification remains pending.
- Planned operating runbooks: `runbooks/restore-openbao.md`, `runbooks/unseal-openbao.md`, `runbooks/operate-talos-kms.md`, `runbooks/operate-vault-bootstrap-kms.md`.
- [OpenBao Raft snapshot API](https://openbao.org/docs/api/system/storage/raft/).
- [Yubico personalization manual](https://developers.yubico.com/yubikey-personalization/Manuals/ykpersonalize.1.html).
