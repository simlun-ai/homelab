# Backup and Restore

**Planned design.** Backup jobs, schedules, and restore runbooks are not implemented or tested.

## Recovery goals

Recover Vault without its original node/disks, a running OpenBao instance, or another homelab cluster. Credentials, decryption/unseal material, encrypted payloads, helpers, and protocol metadata must be independently accessible.

Recovery follows the [secret-handling boundary](security/security.md#secret-handling-boundary), [storage ownership rules](layout.md#provisioning-and-storage-ownership), and [manual startup policy](layout.md#power-loss-shutdown-and-manual-startup).

## OpenBao online backups

**Decision:** Vault's OpenBao uses integrated Raft storage. A scheduled job inside Vault exports application-consistent online Raft snapshots through the snapshot API while OpenBao runs, then uploads them to **Cloudflare R2**.

| Item | Requirement / open decision |
| --- | --- |
| Destination | R2 account, endpoint, bucket, and object naming TBD. |
| Encryption | Keep backups encrypted; additional encryption and key delivery TBD. |
| Transfer | Streaming or server-side staging TBD; no workstation-disk staging. |
| Authentication | Scoped snapshot access and R2 upload credentials; provisioning and lifecycle TBD. |
| Schedule / retention | TBD. |
| Verification | Failed/partial exports or uploads must not count as success. Report failures and prove usability through a separate restore exercise; exact checks TBD. |

Provision job credentials without circular recovery dependencies. R2 restore credentials may differ from upload credentials. Keep public destination/object metadata in the recovery guide; protect actual credentials under the [HMAC wrapping protocol](security/security.md#challenges-derivation-and-wrapped-credentials).

## Independent recovery material

Use the [YubiKey or offline golden-key path](security/security.md#core-secret-foundation). For wrapped secrets, also recover the encrypted payload, root-key generation, and exact identifier/public protocol parameters. Track revisions and explicitly select recovery records under the [rotation policy](security/rotation-and-rollback.md); strong rollback enforcement is deferred. Preserve any independently trusted freshness metadata if introduced later. The [v1 record and rotation rules](security/security.md#updates-rotation-and-recovery) apply.

| Material | Needed for / independence requirement |
| --- | --- |
| R2 restore credentials and wrapped payload | Retrieve snapshots before OpenBao is restored; R2 cannot hold the only copy of its own access payload. |
| OpenBao unseal/recovery material and wrapped payload | Access restored data without the original Vault instance or disks. |
| Additional backup-decryption material, if used | Available before opening the backup. |
| Disk-unlock material | Access surviving or replacement storage without relying on that storage already being unlocked. |
| OpenBao transit key versions and Talos sealed payloads | Restore KMS unlock for Backup, Pi, and Metal; retain every key version needed by surviving disks. |
| KMS adapter configuration/bootstrap credentials | Re-establish its endpoint, TLS, and authorized transit access before dependent nodes unlock. |
| Vault coordinator KMS configuration, wrapped credentials, and sealed disk payloads | Rebuild Vault's independent unlock service without its original coordinator or OpenBao; exact recovery copies/locations and procedure TBD. |
| Talos bootstrap/administration material | Rebuild Vault before its control plane or OpenBao is usable. |
| Helpers, protocol metadata, compatible tools | Obtainable without the failed homelab. |

Wrapped credential records live in the private `homelab-secrets` submodule; coordinator records are also deployed locally under the [storage policy](security/encrypted-record-storage.md). Exact record mappings and other recovery artifacts remain TBD. Proposed credential lookups belong in [yubikey.md](security/yubikey.md); secret custody and handling in [security.md](security/security.md).

## Required recovery targets

Both paths restore OpenBao from an R2 Raft snapshot and independently held, YubiKey-wrapped unseal material. Neither path is implemented or tested.

| Target | Required outcome |
| --- | --- |
| Replacement Raspberry Pi 4 | Rebuild the full single-node Talos Vault cluster, including independent coordinator KMS access, manually managed encrypted ZFS storage, OpenBao, and foundation services. |
| Linux container on a trusted workstation | Recover a temporary single-node OpenBao instance without Talos, Kubernetes, ZFS, or the coordinator; allow recovery access to secrets and transit keys. |

Start with the OpenBao version recorded for the snapshot and a pinned, independently obtainable recovery image/binary. Preserve non-secret server configuration and required plugin/secret references separately: a Raft snapshot is not a complete host or Kubernetes backup.

The container uses a normal Raft-backed server with its storage, snapshot input, secret-bearing configuration, and temporary files on verified memory-backed mounts, not development mode or the in-memory storage backend. Prevent writes to the container's disk-backed writable layer, host volumes, engine credential metadata/logs, swap, hibernation, and dumps. Verify the actual workstation/container runtime, including any VM-backed engine; RAM capacity and exact launch configuration remain TBD. Termination loses the temporary restored state; preserve any required recovery changes as a fresh encrypted snapshot through a compliant transfer before teardown.

Document both branches in `/runbooks/restore-openbao.md`. Prove snapshot retrieval and identity/integrity, the exact initialize/restore/reseal/unseal sequence, recovery administration access, representative secret reads, and transit decryption of previously sealed test material. New-instance unseal material does not replace the material associated with the snapshot; any forced restore bypasses consistency checks, not encryption.

Run isolated restore drills without the original Vault/coordinator or other clusters. Test ARM64 Pi restoration and the actual workstation architecture/runtime, a separately held token and the guide, and the offline golden-key fallback. Record snapshot identity/version, recovery time, required RAM, and verification results without secret output; check workstation-disk compliance. Pi recovery additionally verifies manual-storage preservation, cold boot, dependent-node unlock, and resumed backups.

## Vault restore outline

Recover/verify the [coordinator bootstrap KMS](security/security.md#vault-bootstrap-kms) before Vault system-volume unlock. Router/network, DNS, and public NTP must work independently; Internet is an accepted cold-start dependency. Coordinator-loss recovery and expired-certificate renewal must be tested without OpenBao or workstation-disk plaintext secrets.

Coordinate [Vault installation](installation/02-vault.md), `/runbooks/operate-vault-bootstrap-kms.md`, and `/runbooks/restore-openbao.md` with the [Emergency Recovery Guide's restore outline](emergency-recovery-guide.md#restore-vault-and-openbao).

After restoring OpenBao, verify transit key versions and KMS adapter readiness before starting dependent nodes. Verify snapshot coverage after transit key creation/rotation; an older snapshot may lack keys required by newer disks. The [startup dependency](security/security.md#talos-kms-adapter) must not depend on an encrypted Backup, Pi, or Metal node.

## Wrapped-record backups

Backup storage and procedures for wrapped credential records are deferred until there is material worth backing up. The [Emergency Recovery Guide](emergency-recovery-guide.md) remains a draft; its recovery commands and metadata still need completion and testing.

## Other backup coverage

Other cluster data, manual pools, cluster state, and supporting hosts still need coverage, destination, retention, and restore policies. The inventory's restore disk does not establish such a policy.

## Planned work

Required drill scenarios and completion evidence belong in [recovery procedures](security/recovery-procedures.md). Recovery is verified only after successful testing on the required target.

Implement and test the snapshot/upload job, settle the open decisions above, write the restore runbooks, and complete/distribute the tested recovery guide. YubiKey setup is tracked in [security.md](security/security.md#planned-yubikey-configuration-runbook); the runbook index is in [layout.md](layout.md#central-runbooks).

## Upstream references

- [OpenBao Raft snapshot API](https://openbao.org/docs/api/system/storage/raft/).
- [OpenBao Raft commands](https://openbao.org/docs/commands/operator/raft/).
- [OpenBao security model](https://openbao.org/docs/internals/security/).
- [OpenBao Raft storage configuration](https://openbao.org/docs/configuration/storage/raft/).
- [Docker tmpfs mounts](https://docs.docker.com/engine/storage/tmpfs/) (including host swap caveats).
