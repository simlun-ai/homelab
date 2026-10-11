# Backup and Restore

**Status: planned design.** The policies below are decided where stated. Jobs, scripts, schedules, and detailed runbooks have not been implemented or tested as part of this documentation.

This document owns backup architecture and recovery dependencies. [Security](security.md) owns secret handling and the shared YubiKey HMAC foundation. [Emergency Recovery Guide](emergency-recovery-guide.md) is the non-secret, single-file guide for the USB sticks. [Repository layout](layout.md#central-runbooks) lists planned operating procedures.

## Recovery goals

- Recover Vault without an existing OpenBao service, another homelab cluster, or access to the original node and disks.
- Keep restore credentials, decryption/unseal material, and required encrypted payloads independently recoverable.
- Keep secrets and snapshot contents off workstation disk during backup and restore.
- Preserve all manually managed non-Piraeus ZFS pools; rebuilding a node is not permission to initialize its data disks.
- After a UPS-triggered shutdown, restart manually, one machine at a time, with Vault services available before dependent clusters. Unattended power-return recovery is not required.

## OpenBao online backups

**Decision:** OpenBao in Vault uses integrated Raft storage. A scheduled job inside Vault takes online Raft snapshots through OpenBao's snapshot API while the service remains running, and uploads the snapshots to **Cloudflare R2**.

| Item | Planned behavior |
| --- | --- |
| Backup source | OpenBao's application-consistent Raft snapshot API. |
| Job location | Inside the Vault cluster. |
| Destination | Cloudflare R2; account, endpoint, bucket, and object naming TBD. |
| Encryption | Backups remain encrypted; any additional encryption layer and key delivery are TBD. |
| Workstation handling | No local staging of secrets or snapshot contents. |
| Authentication | Scoped OpenBao snapshot access and scoped R2 upload access; exact provisioning and lifecycle TBD. |
| Schedule and retention | TBD. |
| Success criteria | Snapshot retrieval completes, upload completes, failures are reported, and a separate restore exercise proves usability; exact checks TBD. |

The helper's streaming or server-side staging implementation is TBD. It must propagate failures correctly and must not report a successful backup for a failed or partial transfer. The backup job's own credentials must be provisioned without creating a circular dependence on Vault recovery.

R2 restore access may be different from upload access. Record non-secret destination and object-identification details in the recovery guide, and protect actual credentials under the HMAC foundation described in [security.md](security.md#challenges-derivation-and-wrapped-credentials).

## Independent recovery material

All monorepo core secrets rely on the four interchangeable, touch-required HMAC-SHA1 YubiKeys. Each is planned to be kept at a different location with a USB stick carrying the Emergency Recovery Guide. The separately held offline golden key supports token replacement and software response reproduction.

A working token or the golden key supplies the HMAC foundation. For wrapped secrets, recovery also requires the encrypted payload and exact non-secret protocol metadata. Their independent locations must be decided and tested.

| Required material | Purpose | Independence requirement |
| --- | --- | --- |
| R2 restore credentials and any wrapped payload | Retrieve snapshots. | Available before OpenBao is restored; do not make R2 the only location of its own access payload. |
| OpenBao unseal/recovery material and any wrapped payload | Access restored OpenBao data. | Available without the original Vault instance or disks. |
| Backup-decryption material, if an extra layer is used | Read the snapshot for restoration. | Available before opening the encrypted backup. |
| Disk-unlock material | Access surviving or replacement encrypted storage as required. | Avoid relying on the storage being unlocked. |
| Talos bootstrap/administration material as required by the recovery procedure | Bring up the replacement Vault node. | Available before the original control plane or OpenBao is usable. |
| Recovery helpers, exact protocol metadata, and compatible tool versions | Reproduce derive/unwrap operations. | Obtainable independently of the failed homelab. |

No actual secrets belong in this document, the repository, or the documentation USB sticks. Golden-key custody and protected-payload locations are specified as open implementation decisions in [security.md](security.md#remaining-decisions).

## Vault restore outline

The detailed procedure belongs in `/runbooks/restore-openbao.md`, with node bootstrap covered by `/runbooks/bootstrap-vault.md`. Both paths are planned.

1. Obtain one token/USB-guide pair, or the separately held offline golden key if no token is usable.
2. Prepare a recovery workstation with verified memory-only secret handling and the specified tools.
3. Reproduce the documented challenges, touch the YubiKey when requested, and derive or unwrap the required restore material in memory. With the golden key, use the equivalent software path.
4. Locate an appropriate R2 snapshot, verify the recorded identity/integrity information, and obtain any additional decryption material without workstation-disk staging.
5. Bootstrap replacement Vault infrastructure if necessary, preserving manually managed disks and avoiding dependencies on the service being restored.
6. Restore the Raft snapshot using the documented OpenBao restore procedure and the corresponding unseal/recovery material. Exact initialization, seal, restore, and unseal ordering remain TBD until the detailed runbook is validated.
7. Verify access to expected secrets, authentication/policies, and dependent services, then verify that scheduled backups work.
8. Start dependent clusters deliberately, one machine at a time, after their required Vault services are ready.

Do not assume a newly initialized instance's recovery material can unlock an older snapshot. The validated procedure must identify the seal/unseal material associated with the chosen backup.

## Emergency Recovery Guide custody

Name the documentation kit **Homelab Recovery Kit**. Its initial artifact is the single-file **Emergency Recovery Guide**, [emergency-recovery-guide.md](emergency-recovery-guide.md).

Keep four copies, one on the USB stick paired with each YubiKey at its separate location. The guide contains only documentation and non-secret recovery metadata. Do not include the golden key, responses, plaintext credentials, unseal material, or secret-bearing configurations. Encrypted secret bundles are not part of this documentation-only kit; their independently accessible storage is a separate TBD.

The guide must be readable without the homelab being available. Complete it with exact non-secret protocol parameters, recovery-tool acquisition information, backup locations, and the validated restoration procedure. Its draft must not depend solely on links to repository files that are absent from the USB stick.

Whenever the recovery protocol, tool pins, backup destination, or restore procedure changes, update all four copies and record their revision. Refresh frequency and verification procedure are TBD. Test restoration using a separately held kit, and also test the golden-key software fallback.

## Other backup coverage

Only OpenBao's online Raft snapshot mechanism and R2 destination are decided here. Backup coverage, destinations, retention, and restore procedures for other cluster data, manually managed pools, cluster state, and supporting hosts remain TBD. The hardware restore disk recorded in the inventory does not by itself establish a backup or retention policy.

## Planned work

- Implement and test the in-cluster OpenBao snapshot/upload job.
- Define schedule, retention, encryption, authentication, failure reporting, and restore verification.
- Write the Vault bootstrap and OpenBao restore runbooks with a tested seal/restore sequence.
- Write `/runbooks/configure-yubikey-challenge-response.md` as specified in [security.md](security.md#planned-yubikey-configuration-runbook).
- Define independent protected-payload storage and complete the Emergency Recovery Guide.
- Verify both recovery using any one of the four tokens and the separately held golden-key fallback, without workstation-disk secrets.

## Upstream references

- [OpenBao Raft snapshot API](https://openbao.org/docs/api/system/storage/raft/): snapshot export and restore.
- [OpenBao Raft commands](https://openbao.org/docs/commands/operator/raft/): snapshot save/restore commands and restore checks.
- [OpenBao security model](https://openbao.org/docs/internals/security/): encrypted storage and seal material.
