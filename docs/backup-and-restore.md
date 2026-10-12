# Backup and Restore

**Planned design.** Backup jobs, schedules, and restore runbooks are not implemented or tested.

## Recovery goals

Recover Vault without its original node/disks, a running OpenBao instance, or another homelab cluster. Credentials, decryption/unseal material, encrypted payloads, helpers, and protocol metadata must be independently accessible.

Recovery follows the [secret-handling boundary](security.md#secret-handling-boundary), [storage ownership rules](layout.md#provisioning-and-storage-ownership), and [manual startup policy](layout.md#power-loss-shutdown-and-manual-startup).

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

Provision job credentials without circular recovery dependencies. R2 restore credentials may differ from upload credentials. Keep public destination/object metadata in the recovery guide; protect actual credentials under the [HMAC wrapping protocol](security.md#challenges-derivation-and-wrapped-credentials).

## Independent recovery material

Use the [YubiKey or offline golden-key path](security.md#core-secret-foundation). For wrapped secrets, also recover the encrypted payload and exact public protocol parameters.

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

Protected-payload locations remain TBD. Secret custody and handling belong in [security.md](security.md).

## Vault restore outline

Recover/verify the [coordinator bootstrap KMS](security.md#vault-bootstrap-kms) before Vault system-volume unlock. Router/network, DNS, and public NTP must work independently; Internet is an accepted cold-start dependency. Coordinator-loss recovery and expired-certificate renewal must be tested without OpenBao or workstation-disk secrets.

Plan `/runbooks/operate-vault-bootstrap-kms.md`, `/runbooks/bootstrap-vault.md`, and `/runbooks/restore-openbao.md` around the [Emergency Recovery Guide's restore outline](emergency-recovery-guide.md#restore-vault-and-openbao).

Validate snapshot identity/integrity, replacement-node bootstrap, the exact initialization/seal/restore/unseal sequence, expected secrets and authentication/policies, dependent Vault services, and resumed backups. Use the seal/unseal material associated with the selected snapshot; newly initialized material must not be assumed to unlock an older backup.

After restoring OpenBao, verify transit key versions and KMS adapter readiness before starting dependent nodes. Include a cold-boot unlock test and snapshot coverage after transit key creation/rotation; an older snapshot may lack keys required by newer disks. The [startup dependency](security.md#talos-kms-adapter) must not depend on an encrypted Backup, Pi, or Metal node.

Test recovery from a separately held token/guide pair and through the golden-key software fallback, without workstation-disk secrets.

## Emergency Recovery Guide custody

The **Homelab Recovery Kit** starts with one non-secret, standalone [Emergency Recovery Guide](emergency-recovery-guide.md) on each token's paired USB stick. Token and golden-key custody belong in [security.md](security.md#core-secret-foundation).

The documentation-only kit excludes secrets, secret-bearing configuration, and encrypted secret bundles; store protected payloads separately with independent access. Complete the guide with exact public protocol parameters, tool acquisition, backup locations, and validated recovery commands. It must work without other local documents or the homelab.

After protocol, tool-pin, destination, or procedure changes, refresh every copy and record its revision. Refresh frequency and verification procedure remain TBD.

## Other backup coverage

Other cluster data, manual pools, cluster state, and supporting hosts still need coverage, destination, retention, and restore policies. The inventory's restore disk does not establish such a policy.

## Planned work

Implement and test the snapshot/upload job, settle the open decisions above, write the restore runbooks, and complete/distribute the tested recovery guide. YubiKey setup is tracked in [security.md](security.md#planned-yubikey-configuration-runbook); the runbook index is in [layout.md](layout.md#central-runbooks).

## Upstream references

- [OpenBao Raft snapshot API](https://openbao.org/docs/api/system/storage/raft/).
- [OpenBao Raft commands](https://openbao.org/docs/commands/operator/raft/).
- [OpenBao security model](https://openbao.org/docs/internals/security/).
