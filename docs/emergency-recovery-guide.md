# Emergency Recovery Guide

**Homelab Recovery Kit — non-secret, single-file draft.** For recovering Vault and OpenBao when the original hardware or services are unavailable.

Exact commands and recovery metadata must be completed and tested before use. Essential instructions are included here because the USB copy must work without other local documents.

## Revision and recovery metadata

All entries must be non-secret.

| Field | Value |
| --- | --- |
| Guide revision / repository commit; last verified restore | TBD. |
| Core-secret protocol version and YubiKey HMAC slot | TBD; touch required. |
| Effective challenge bytes, encoding, purpose identifiers, length/padding | TBD; match tokens and software fallback. |
| Derivation/wrapping algorithms, output encoding, public parameters | TBD. |
| Compatible OpenBao and recovery-tool versions; independent acquisition locations | TBD. |
| Tool and backup integrity/checksum verification | TBD. |
| R2 account, endpoint, bucket, object convention; snapshot selection | TBD. |
| Additional backup-encryption details | TBD. |
| Independent encrypted-payload references | TBD; accessible without Vault or existing R2 credentials. |
| Golden-key retrieval procedure reference | TBD; never record the key here. |
| Vault coordinator KMS endpoint, public TLS/DNS-01, preboot DNS/NTP, session controls | TBD; include service acquisition, independent wrapped-payload references, and coordinator rebuild instructions. |
| KMS adapter endpoint, TLS trust, early-boot networking, transit key mapping/versions | TBD; include adapter acquisition and independent bootstrap-payload references. |
| Per-device power-return limitations and manual startup procedure | TBD. |

## Required access and operating rules

Use one working YubiKey and its paired USB guide, independently stored encrypted recovery payloads, and a recovery workstation with the specified tools. All homelab secrets are rooted in the 20-byte golden key through derivation, wrapping, or OpenBao protected by wrapped unseal material. All four tokens share the golden key and HMAC-SHA1 settings and are kept at separate locations; identical effective challenges produce identical responses. One token suffices; if none works, obtain the separately held offline golden key.

- Keep the documentation USB non-secret: no golden key, HMAC responses, derived values, credentials, unseal shares, private keys, secret-bearing configuration, or encrypted secret bundles.
- Never write secrets or snapshots to workstation disk, including temporary files, caches, shell history, logs, state, or saved plans. Verify memory-only handling, including swap, hibernation, subprocesses, and failure paths.
- Hardware challenge-response requires touch; the golden-key software fallback cannot enforce it.
- Preserve manual non-Piraeus ZFS pools during node installation or repair; do not wipe or initialize them.
- Vault recovery must work without its failed OpenBao instance or another cluster. Its system-volume KMS runs independently on the Vault/Backup coordinator; public NTP/Internet is an accepted cold-start dependency. DNS API and TLS private-key payloads are encrypted at rest and unwrapped into coordinator memory after YubiKey touch. KMS unlock authority lasts only for a short boot session; duration TBD. Communication uses TLS on a trusted network; additional host-to-host network hardening remains TBD.
- After UPS-triggered shutdown, power machines on manually, one at a time, with Vault services ready before dependent clusters. Disable automatic power-return startup and wake sources where supported; account for device limitations.

## Recover core-secret access

1. Select the recorded HMAC slot and protocol version. Obtain the specified helper and verify its integrity.
2. Load the exact public challenge and derivation/wrapping parameters.
3. Query the token and touch it; keep responses and subsequent secret values in memory.
4. Derive or unwrap R2 access, backup-decryption, OpenBao unseal/recovery, and node bootstrap/unlock material using the independent payloads. HMAC alone cannot recreate externally issued credentials or OpenBao-generated material.

If a token fails, obtain another token/guide pair. Never guess encoding or overwrite an occupied slot.

## Golden-key fallback and replacement token

Retrieve the offline golden key using its separate custody procedure. Load it into the verified memory-only session without logging. The helper must compute HMAC-SHA1 over identical effective challenge bytes, then apply the same derivation/unwrap steps.

Replacement programming must use the same key/settings with **touch required**, preserve occupied slots unless explicitly approved, verify behavior, record the non-secret device identity, and return a current token/guide pair to its location. Exact helper acquisition, programming commands, and verification steps remain TBD.

## Restore Vault and OpenBao

OpenBao backups are online Raft snapshots uploaded by a job inside Vault to Cloudflare R2.

1. Recover R2 access and any wrapped/decryption material.
2. Select a snapshot and validate its recorded identity/integrity; do not stage it on workstation disk.
3. Recover/start the coordinator and establish time, DNS, and valid public KMS TLS. Touch a YubiKey to enable its independent KMS boot session, then bootstrap/unlock single-node Talos Vault infrastructure as needed, preserving manual ZFS storage. Coordinator rebuild, expired-certificate renewal, and exact commands remain TBD.
4. Restore the snapshot with its corresponding seal/unseal material. Use the workstation helper and a touched YubiKey (or the software fallback) to unwrap and submit the required unseal material in memory. **Exact initialization, restore, and unseal ordering is TBD and must be validated; new-instance material may not unlock an older snapshot.**
5. Verify expected secrets, authentication/policies, certificate distribution, and resumed encrypted snapshot uploads to R2.
6. Restore/verify the Python gRPC KMS adapter and required OpenBao transit key versions. Backup, Pi, and Metal need this service to unlock Talos system volumes; Vault must unlock independently. An older snapshot may lack transit keys required by newer disks. Verify early-boot network access and TLS trust before starting nodes.
7. Start dependent clusters manually, one machine at a time, checking KMS unlock, dependencies, and storage.

## Complete before distributing a usable kit

Fill every recovery-critical field and embed exact acquisition, operating, and failure-handling commands in this file. Test touch enforcement and matching responses across all tokens and the software fallback without recording secret output. Prove an R2 restore with a separately held token/guide pair and with the golden-key fallback. Refresh every USB copy after relevant changes.

## Maintenance references

These references do not replace embedded emergency instructions.

- Policies: `docs/security.md` and `docs/backup-and-restore.md`.
- Planned runbooks: `runbooks/configure-yubikey-challenge-response.md`, `runbooks/bootstrap-vault.md`, `runbooks/restore-openbao.md`, `runbooks/unseal-openbao.md`, `runbooks/operate-talos-kms.md`, `runbooks/operate-vault-bootstrap-kms.md`.
- [OpenBao Raft snapshot API](https://openbao.org/docs/api/system/storage/raft/).
- [Yubico personalization manual](https://developers.yubico.com/yubikey-personalization/Manuals/ykpersonalize.1.html).
