# 02 - Vault

**Placeholder; not yet implemented or verified.**

Install the independent Vault cluster after the [main coordinator](01-main-coordinator.md) is ready.

## TODO

- [ ] Validate Talos installation, boot, MD RAID1, and KMS encryption on the assigned OS disks; implement the pinned tooling and Vault bootstrap configuration.
- [ ] Document manual encrypted ZFS mirror preparation and deploy the planned platform services and OpenBao, including workstation/YubiKey unseal support.
- [ ] Verify cold startup, scheduled Raft snapshot backups, and the required restore paths; record results and update the recovery guide.

References: [Vault architecture](../clusters.md#vault), [hardware and disks](../inventory.md#vault), [repository layout](../layout.md#common-cluster-layout), [OpenBao unseal](../security/openbao-unseal.md), [backup and recovery](../backup-and-restore.md).
