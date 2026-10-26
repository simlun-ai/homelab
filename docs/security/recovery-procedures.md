# Recovery procedures

**Recovery requirements approved; commands and drills pending.**

Exact operating commands belong in the central runbooks and the standalone
[Emergency Recovery Guide](../emergency-recovery-guide.md).
[Backup architecture](../backup-and-restore.md) owns snapshot storage
and restore targets.

## Required scenarios

| Scenario | Required proof |
| --- | --- |
| Token failure | Recover with another token; separately test the Level 1 golden-key software fallback. |
| Coordinator loss | Rebuild without Vault/OpenBao, deploy wrapped records, restore independent SSH access and verified host identity, and authorize the existing node KMS key from the workstation. |
| Vault loss | Restore to a replacement Raspberry Pi 4, preserving manual storage and restoring OpenBao from R2 with the corresponding unseal material. |
| Emergency secret access | Restore OpenBao into a RAM-backed Linux container on a trusted workstation, without the original Vault or coordinator. |

Perform drills in isolation from production integrations and without
relying on the failed infrastructure. Keep secrets and snapshots off
workstation disk under the [handling policy](security.md#secret-handling-boundary).

Internet access for R2, DNS, and public NTP remains an accepted dependency.
Recovery tooling must be independently available under the
[helper design](helper-implementation.md). Retain `tools/homelab-hsm/homelab_secrets/` and the private `secrets/wrapped/` records checkout; a parent-only checkout cannot run wrap/unwrap. Source clones alone are not sufficient: prepare the scoped environment and pinned dependencies before going offline. The standalone code project includes offline wheel bundles; integrating independent recovery tooling and testing recovery drills remain pending.

## Evidence and completion

Record the repository commit, snapshot identity, required key generations,
tool versions, test result, and recovery time without secret output.

Verify administrative access and representative secret reads. Where
applicable, also verify disk unlock, transit decryption, manual-storage
preservation, and resumed backups.

A recovery procedure is complete only after successful testing on its
required target. Written commands alone do not establish verified recovery.

## Remaining implementation work

Write and test acquisition, coordinator rebuild, Pi and container restore,
and failure-handling commands. Record actual hardware/runtime
details and resource requirements; complete the standalone recovery guide.
