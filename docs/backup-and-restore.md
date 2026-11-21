# Backup and Restore

**OpenBao backup implementation is ready for live verification.** Other backup jobs and restore procedures remain planned.

## Recovery goals

Recover Trust without its original node/disks, a running OpenBao instance, or another homelab cluster. Credentials, decryption/unseal material, encrypted payloads, helpers, and protocol metadata must be independently accessible.

Recovery follows the [secret-handling boundary](security/security.md#secret-handling-boundary), [storage ownership rules](layout.md#provisioning-and-storage-ownership), and [manual startup policy](layout.md#power-loss-shutdown-and-manual-startup).

## OpenBao online backups

**Decision:** Trust's OpenBao uses integrated Raft storage. A scheduled job inside Trust exports application-consistent online Raft snapshots through the snapshot API while OpenBao runs, then backs them up with restic directly to **Cloudflare R2**. The [Trust snapshot milestone](installation/trust-openbao-backups.md) covers the scheduled backup, automatic sealed restore, and YubiKey verification on the existing Trust cluster.

| Item | Requirement / open decision |
| --- | --- |
| Destination | Private R2 bucket with a dedicated restic repository. Account, endpoint, bucket, and repository path TBD. |
| Encryption | Restic encrypts the repository. Keep its password independently recoverable. |
| Transfer | Stage the Raft snapshot on Trust in bounded memory-backed storage and back it up directly to R2. |
| Authentication | Scoped snapshot access and R2 upload credentials; provisioning and lifecycle TBD. |
| Schedule / retention | Daily at 02:30 UTC. Restic retention and pruning remain operator-managed. |
| Verification | Failed/partial exports or uploads must not count as success. Report failures and prove usability through a separate restore exercise; exact checks TBD. |

Provision job credentials without circular recovery dependencies. R2 restore credentials may differ from upload credentials. Keep public destination/object metadata in the recovery guide; protect actual credentials under the [HMAC wrapping protocol](security/security.md#challenges-derivation-and-wrapped-credentials).

The operator will regularly copy all R2 data to a drive kept offline between runs. Preserve a previous usable copy when refreshing the encrypted repository so deletions in R2 do not erase the offline recovery point.

## Independent recovery material

Use the [YubiKey or offline golden-key path](security/security.md#core-secret-foundation). For wrapped secrets, also recover the encrypted payload, root-key generation, and exact identifier/public protocol parameters. Track revisions and explicitly select recovery records under the [rotation policy](security/rotation-and-rollback.md); strong rollback enforcement is deferred. Preserve any independently trusted freshness metadata if introduced later. The [v1 record and rotation rules](security/security.md#updates-rotation-and-recovery) apply.

| Material | Needed for / independence requirement |
| --- | --- |
| R2 restore credentials and wrapped payload | Retrieve snapshots before OpenBao is restored; R2 cannot hold the only copy of its own access payload. |
| OpenBao unseal/recovery material and wrapped payload | Access restored data without the original Trust instance or disks. |
| Restic repository password | Recover independently before opening an R2 or offline repository copy. |
| Disk-unlock material | Access surviving or replacement storage without relying on that storage already being unlocked. |
| OpenBao transit key versions and Talos sealed payloads | Restore KMS unlock for Backup, Pi, and Metal; retain every key version needed by surviving disks. |
| KMS adapter configuration/bootstrap credentials | Re-establish its endpoint, TLS, and authorized transit access before dependent nodes unlock. |
| Trust coordinator KMS configuration, wrapped credentials, and sealed disk payloads | Rebuild Trust's independent unlock service without its original coordinator or OpenBao; exact recovery copies/locations and procedure TBD. |
| Talos bootstrap/administration material | Rebuild Trust before its control plane or OpenBao is usable. |
| Helpers, protocol metadata, compatible tools | Obtainable without the failed homelab. |

Wrapped credential records live in the private `homelab-secrets` submodule; coordinator records are also deployed locally under the [storage policy](security/encrypted-record-storage.md). Recreatable coordinator ACME/TLS state is an exception: its ciphertext and archives live only on the coordinator; SD-card loss uses explicit recreation with the preserved Cloudflare credential. Exact mappings for other recovery artifacts remain TBD. Proposed credential lookups belong in [yubikey.md](security/yubikey.md); secret custody and handling in [security.md](security/security.md).

## OpenBao disaster recovery rehearsal

The sole OpenBao restore test uses a disposable second instance on the
existing Trust Pi Kubernetes cluster. Restore a snapshot retrieved from R2
using the matching YubiKey-wrapped unseal material. The rehearsal verifies
OpenBao recovery from backup on a functioning cluster. It depends on Trust
Kubernetes being available.

Use the [Trust backup operator runbook](installation/trust-openbao-backup-operations.md). Prove
snapshot retrieval and integrity, the initialization and restore sequence,
unseal, administrative access, and readback of the known fixture. Include
transit decryption once transit is in use. Record the snapshot identity,
OpenBao version, recovery time, resource usage, and outcome without secrets.
See the [Trust restore plan](installation/trust-openbao-backups.md#disaster-recovery-rehearsal-on-trust).

## Trust restore outline

Recover/verify the [coordinator bootstrap KMS](security/security.md#trust-bootstrap-kms) before Trust system-volume unlock. Router/network, DNS, and public NTP must work independently; Internet is an accepted cold-start dependency. Coordinator-loss recovery and expired-certificate renewal must be tested without OpenBao or workstation-disk plaintext secrets. The [draft KMS recovery gate](security/trust-bootstrap-kms.md#independent-coordinator-loss-recovery-gate) proposes rebuilding from preserved wrapped node-key generations and lists the still-unresolved recovery copies, locations, UUID-change and LUKS-header requirements; it does not establish a working restore procedure.

Coordinate [Trust installation](installation/02-trust.md), `/runbooks/operate-trust-bootstrap-kms.md`, and the [OpenBao backup runbook](installation/trust-openbao-backup-operations.md) with the [Emergency Recovery Guide's restore outline](emergency-recovery-guide.md#restore-trust-and-openbao).

After restoring OpenBao, verify transit key versions and KMS adapter readiness before starting dependent nodes. Verify snapshot coverage after transit key creation/rotation; an older snapshot may lack keys required by newer disks. The [startup dependency](security/security.md#talos-kms-adapter) must not depend on an encrypted Backup, Pi, or Metal node.

## Wrapped-record backups

Backup storage and procedures for wrapped credential records are deferred until there is material worth backing up. The [Emergency Recovery Guide](emergency-recovery-guide.md) remains a draft; its recovery commands and metadata still need completion and testing.

## Other backup coverage

Garage is planned on the Backup cluster for periodic backups. Its HTTPS endpoint will be the first consumer of Trust's [certificate factory](clusters.md#certificate-factory). Its coverage, clients, schedules, retention, and restore procedures remain TBD. Trust's OpenBao Raft snapshots use Cloudflare R2 as described above. Manual pools, cluster state, and supporting hosts still need explicit coverage. The inventory's restore disk does not establish a backup policy.

## Planned work

Required drill scenarios and completion evidence belong in [recovery procedures](security/recovery-procedures.md). Recovery is verified only after successful testing on the required target.

Implement and test the snapshot/upload job, settle the open decisions above, write the restore runbooks, and complete/distribute the tested recovery guide. YubiKey setup is tracked in [security.md](security/security.md#yubikey-configuration-runbook); the runbook index is in [layout.md](layout.md#central-runbooks).

## Upstream references

- [OpenBao Raft snapshot API](https://openbao.org/docs/api/system/storage/raft/).
- [OpenBao Raft commands](https://openbao.org/docs/commands/operator/raft/).
- [OpenBao security model](https://openbao.org/docs/internals/security/).
- [OpenBao Raft storage configuration](https://openbao.org/docs/configuration/storage/raft/).
- [Docker tmpfs mounts](https://docs.docker.com/engine/storage/tmpfs/) (including host swap caveats).
