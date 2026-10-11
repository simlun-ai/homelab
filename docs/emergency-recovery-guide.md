# Emergency Recovery Guide

**Homelab Recovery Kit — non-secret single-file guide, initial draft.**

Purpose: recover the homelab's foundational Vault cluster and its OpenBao backups when the original node, disks, or running services are unavailable. Keep this single file on a USB stick with each of the four YubiKeys, with the four token/guide pairs at different locations.

This draft records the agreed design and the fields to complete. Exact commands and metadata must be added and verified before the guide can serve as a complete emergency procedure.

## Revision and recovery metadata

| Field | Value |
| --- | --- |
| Guide revision / repository commit | TBD when this kit is prepared. |
| Last verified restore | TBD. |
| Core-secret protocol version | TBD. |
| YubiKey HMAC slot | TBD; physical touch is required. |
| Effective challenge bytes and encoding for each recovery role | TBD; record exact public values and purpose identifiers. |
| Challenge length/padding settings | TBD; must match all four tokens and the software fallback. |
| Downstream derivation/wrapping algorithm and non-secret parameters | TBD. |
| OpenBao version compatible with the selected backup | TBD. |
| Recovery tool versions and independent acquisition locations | TBD. |
| Integrity/checksum verification for tools and backup artifacts | TBD. |
| R2 account, endpoint, bucket, and snapshot object convention | TBD; no credentials here. |
| Independent locations/references for required encrypted recovery payloads | TBD; include a route that works without Vault and without R2 credentials. |
| Snapshot selection and additional encryption details | TBD. |
| Golden-key retrieval procedure reference | TBD; never record the key here. |
| Device power-return limitations and manual startup procedure | TBD per device. |

All values added to this table must be non-secret. HMAC responses and derived values are secret even when the challenge itself is public.

## What accompanies this guide

- One of four YubiKeys programmed with the same HMAC-SHA1 golden key and matching challenge settings.
- A USB stick containing this guide only as the initial documentation kit.
- Access to the independently stored encrypted recovery payloads, if the selected protocol wraps existing credentials.
- Access to a suitable recovery workstation and the specified tools.
- If no token is usable, access to the separately held offline golden key and the software fallback procedure.

The golden key is held separately offline. Do not store it on this USB stick or in this guide. Do not put credentials, unseal shares, HMAC responses, private keys, or secret-bearing configuration files on the documentation USB stick.

## Operating rules

1. Never write secrets or snapshot contents to the recovery workstation's disk, including temporary files, the checkout, shell history, logs, caches, or saved plans. Use verified memory-only handling; account for swap, hibernation, and failure paths.
2. A token challenge-response operation requires physical touch. The software fallback uses the separately held golden key and has no hardware touch requirement.
3. Preserve non-Piraeus ZFS data disks and pools. Do not let node installation initialize or wipe them.
4. After a UPS-triggered shutdown, start machines manually, one at a time. Bring Vault services up before dependent clusters. Disable automatic power-return startup and automatic wake sources where supported.
5. Vault recovery must not require the failed OpenBao service or another homelab cluster.

## Recover core-secret access

1. Identify the intended HMAC slot and the protocol version from the metadata table.
2. Load the required public challenge and downstream parameters using the specified helper.
3. Query one YubiKey and touch it when requested. Keep the response and subsequent secret values in memory.
4. Derive secret values or unwrap the independently stored payloads according to the recorded protocol. An HMAC response alone cannot recreate externally issued credentials or OpenBao-generated unseal material.
5. Make R2 access, required backup-decryption material, OpenBao unseal/recovery material, and node bootstrap/unlock material available to the restore operation without writing them to workstation disk.

If the token is lost or fails, use a token/guide pair from another location. All four tokens are intended to produce identical responses for identical effective challenges. If no token is usable, use the golden-key fallback below.

## Golden-key fallback and replacement token

Retrieve the separately held offline golden key using its custody procedure. Load it into the verified memory-only session without logging it. The fallback helper must compute HMAC-SHA1 over the exact same effective challenge bytes, then perform the same derivation/unwrap steps.

Use the same key to program replacement tokens under the configuration runbook, with matching challenge settings and **touch required**. Record the replacement's non-secret identity and return a token/guide pair to the appropriate location.

Exact helper acquisition, commands, slot selection, and verification steps are TBD. Do not guess challenge encoding or overwrite an occupied slot during recovery.

## Restore Vault and OpenBao

1. Recover access to the R2 destination and any wrapped/decryption material using the steps above.
2. Select the required online Raft snapshot. Record its non-secret identity and validate the specified integrity information.
3. Obtain replacement hardware if needed and bootstrap the single-node Talos Vault cluster using the validated procedure. Preserve existing manual ZFS data storage.
4. Restore OpenBao's Raft snapshot through the validated restore procedure. Use the seal/unseal material associated with that backup. The exact initialization, restore, and unseal sequence is TBD.
5. Verify access to expected secrets and authentication/policies; then verify certificate distribution and other required Vault services.
6. Confirm that the in-cluster snapshot job can upload new encrypted backups to R2.
7. Start dependent clusters manually, one machine at a time, checking each cluster's dependencies and storage.

OpenBao backups are scheduled online Raft snapshots uploaded by a job inside Vault to Cloudflare R2. No existing Vault service is required to retrieve the emergency access material.

## Complete before distributing a usable kit

- Fill every recovery-critical metadata field with verified non-secret values.
- Embed the exact tool acquisition and operating steps here so this file is usable without other local documentation files.
- Complete and test the detailed Vault/OpenBao restore sequence, including failure handling.
- Verify touch enforcement and equivalent responses on all four tokens without recording responses in the kit.
- Verify an actual restore from R2 using a separate token/guide pair.
- Verify that the golden-key software fallback reproduces the same recovery path.
- Copy the same current guide to all four paired USB sticks after every relevant change.

## Reference locations

These links help maintain the guide but must not become its only source of emergency instructions.

- Security policy: `docs/security.md`.
- Backup architecture: `docs/backup-and-restore.md`.
- Planned YubiKey setup procedure: `runbooks/configure-yubikey-challenge-response.md`.
- Planned Vault bootstrap procedure: `runbooks/bootstrap-vault.md`.
- Planned OpenBao restore procedure: `runbooks/restore-openbao.md`.
- [OpenBao Raft snapshot API](https://openbao.org/docs/api/system/storage/raft/).
- [Yubico personalization tool manual](https://developers.yubico.com/yubikey-personalization/Manuals/ykpersonalize.1.html).
