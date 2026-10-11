# Agent Instructions

These instructions apply to the entire homelab repository.

## Working in this repository

- Treat the current GitHub repository as the source of truth for the homelab. Read the relevant files before editing; do not rely solely on prior conversation or assumptions about the current state.
- Make focused, minimal changes that preserve existing content and conventions unless the user requests a broader reorganization.
- Implement requested repository changes directly when authorized, and report which files changed and the resulting commit or pull request.
- Distinguish **planned**, **configured**, and **deployed** infrastructure. Do not present a proposed configuration as already running.
- Do not invent hardware details, network settings, installed versions, capacities, or deployment status. Use `TBD` or explicitly note unknowns when appropriate.

## Keep documentation synchronized

**Cross-document consistency is a requirement of every change, not an optional cleanup.**

- Check all related documentation when changing any documented fact or structure. Update affected files together, even if the user mentions only one file.
- Keep cluster names, section ordering, node roles, storage layouts, disk quantities, hardware specifications, software components, and architecture consistent wherever they appear.
- In particular, `docs/inventory.md` and `docs/clusters.md` must use the same cluster hierarchy and ordering: **Vault**, **Backup**, **Pi**, **Metal**. These should be second-level headings (`##`) in both documents. Preserve matching names if clusters are added or renamed.
- When a component is added, removed, renamed, or its version changed, check both `docs/components.md` and the relevant cluster documentation. A catalog entry alone does not establish that the component is deployed.
- When hardware, disks, pools, or assignments change, update `docs/inventory.md` and any affected architectural descriptions in `docs/clusters.md`.
- Resolve contradictions rather than leaving documents with competing descriptions. If the correct value cannot be established, identify the discrepancy instead of guessing.

## Documentation responsibilities

- `docs/inventory.md`: Physical machines, cluster membership, hardware, network interfaces, disks, OS and storage layout, spares, shared equipment, and aggregate inventory counts.
- `docs/clusters.md`: Kubernetes cluster topology, dependencies, platform services, networking, storage integration, backup and secrets architecture.
- `docs/components.md`: Software/component catalog and versions, separated into **Infrastructure** and **Workloads**.
- `docs/layout.md`: Draft repository structure, configuration ownership, tooling scopes, automation boundaries, and open implementation decisions.

Use a consistent vocabulary and capitalization for cluster names and components. Preserve precise ZFS pool names, disk models, capacities, redundancy schemes, and node assignments.

## Inventory and capacity rules

- Keep the inventory summary synchronized with the detailed entries whenever equipment changes: raw disk capacity, usable capacity after mirroring, spare-disk capacity and count, RAM, computer count, and disk count.
- Use **decimal disk units** (`1 TB = 1,000 GB`) as the inventory currently does.
- Compute mirror usable capacity from the smaller member of each mirrored pair; account separately for single-disk pools and other explicitly documented layouts.
- Exclude spare drives and cold-spare disks from the usable-capacity total as documented. Do not count additional Piraeus replication as physical mirror capacity, and do not silently change the inventory's counting assumptions.
- Keep OS disks, data disks, spare drives, cold spares, and external/legacy disks distinguishable.

## Architecture invariants to preserve

- **Vault** is the independent foundational cluster; other clusters depend on services it supplies. Avoid circular dependencies: its own secrets are entered manually rather than fetched from its OpenBao instance.
- Keep intended configuration details (for example Flannel versus Cilium, storage technology, and certificate distribution) aligned between cluster architecture and component documentation.
- Describe backups, security-sensitive configuration, and external dependencies accurately without committing actual credentials or secrets.
- Vault's OpenBao backup plan uses integrated Raft storage and scheduled online Raft snapshots uploaded to Cloudflare R2 by a job inside Vault. Preserve independently accessible unseal/recovery material and keep secrets and snapshots off workstation disk.
- Preserve the hard rule that secrets are neither committed nor written to workstation disk, including the checkout, temporary files, caches, and logs. Encrypted persistence in cluster services and backups is allowed; secret handling on the workstation must remain memory-only as described in `docs/layout.md`.
- All four Kubernetes clusters target Talos Linux. Each cluster owns its tool-version pins and `bin/` directory, selected through Makefiles; do not silently fall back to global tools.
- All ZFS storage must be encrypted; OS disk encryption is a goal whose implementation is still TBD. Do not describe these goals as verified deployment state.
- Non-Piraeus ZFS data disks and pools are prepared and repaired manually. Automatic provisioning must not wipe, format, recreate, or destroy them; OS and Piraeus preparation must stay within explicit disk assignments.
- After a UPS-triggered shutdown, recovery is manual: the operator starts systems one at a time. Preserve stay-off behavior after power restoration and disable Wake-on-LAN and other automatic wake sources where supported. Document hardware limitations rather than assuming support; do not introduce unattended power-on as a requirement. Vault services precede dependent clusters during startup.

## Before completing a change

1. Re-read the changed sections and the corresponding sections of related files.
2. Verify headings, names, quantities, storage topology, and references agree across documents.
3. Recalculate affected inventory totals and check the assumptions stated alongside them.
4. Ensure no unrelated information was removed and no planned item was incorrectly labeled deployed.
5. Summarize the changes and any remaining uncertainties.
