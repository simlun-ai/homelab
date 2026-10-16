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
- `docs/layout.md`: Draft repository structure, configuration ownership, tooling scopes, automation boundaries, and links to detailed policies.
- `docs/installation/README.md`: Main installation and implementation TODO list, step order, and progress. Numbered `docs/installation/NN-<headline>.md` runbooks own prerequisites, executable steps, verification results, and recovery actions. Shared UPS coordinator base setup lives in `runbooks/ups-coordinator-base-setup.md`; step 01 links to it and owns only the additional Vault Talos KMS setup. Develop helpers and repository structure as each step is tried; distinguish written instructions, implemented code, and verified installation. Link to architecture and policy rather than duplicating them.
- `docs/security/security.md`: Authoritative core-secret/YubiKey foundation, golden-key custody, workstation secret handling, encryption intent, and security implementation decisions.
- `docs/security/yubikey.md`: Credential/use-case catalogue and finalization/maintenance rules, lookup identifiers and challenge construction, direct versus OpenBao-mediated access, and unresolved bootstrap coverage. Keep proposed identifiers distinct from implemented lookups.
- Other `docs/security/*.md` topic files: Approved topic decisions and remaining TBD work, indexed in `docs/security/security.md`. `encrypted-record-storage.md` owns ciphertext storage, recovery USB clones, and coordinator deployment. Preserve established policy and catalogue ownership while developing them.
- `docs/backup-and-restore.md`: Authoritative backup architecture, independent recovery dependencies, and restore planning.
- `docs/emergency-recovery-guide.md`: Single-file non-secret USB recovery guide; keep it usable independently of other local documents once completed.

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
- Vault's OpenBao backup plan uses integrated Raft storage and scheduled online Raft snapshots uploaded to Cloudflare R2 by a job inside Vault. Preserve independently accessible unseal/recovery material and keep decrypted secrets and snapshots off workstation disk.
- Helpers must never commit plaintext secrets, golden-key material, HMAC responses, or derived keys, or explicitly write them to workstation disk, including temporary files, caches, and logs. The trusted air-gapped step 00 laptop retains its existing OS swap/suspend settings under `docs/security/security.md`; do not reintroduce a swap-disable requirement there. Authenticated `homelab-wrap-v1` credential records may be committed and persisted under `docs/security/encrypted-record-storage.md`; decrypted secret handling stays in process memory. OpenBao snapshots remain excluded from workstation disk; encrypted persistence in cluster services and backups is allowed.
- All homelab secrets are rooted in the 20-byte golden key through direct derivation, HMAC-based wrapping, or OpenBao protected by wrapped unseal material. Four interchangeable HMAC-SHA1 challenge-response YubiKeys share that key/settings with touch required. Each token is paired with a recovery USB containing full parent and private-submodule clones, including wrapped records and the non-secret Emergency Recovery Guide, at a separate location. The golden key is held separately offline for replacement tokens and software recovery. Keep security implementation and custody decisions in `docs/security/security.md`, and lookup identifiers/challenge construction in `docs/security/yubikey.md`; never place actual key material or responses in documentation.
- All four Kubernetes clusters target Talos Linux. Each cluster owns its tool-version pins and `bin/` directory, selected through Makefiles; do not silently fall back to global tools.
- All ZFS storage must be encrypted. Backup, Pi, and Metal plan Talos KMS-backed system-volume encryption through a Python gRPC adapter using OpenBao transit. Vault plans independent system-volume unlock through a YubiKey-backed KMS service on its UPS coordinator; preserve its bootstrap and trusted-network decisions in `docs/security/security.md`. Preserve the startup/recovery dependencies in `docs/security/security.md`, and do not describe planned encryption as verified deployment state.
- Non-Piraeus ZFS data disks and pools are prepared and repaired manually. Automatic provisioning must not wipe, format, recreate, or destroy them; OS and Piraeus preparation must stay within explicit disk assignments.
- After a UPS-triggered shutdown, recovery is manual: the operator starts systems one at a time. Preserve stay-off behavior after power restoration and disable Wake-on-LAN and other automatic wake sources where supported. Document hardware limitations rather than assuming support; do not introduce unattended power-on as a requirement. Vault services precede dependent clusters during startup.

## Wrapped-record repository boundary

- The golden key uses OTP HMAC-SHA1 slot 2 on all four YubiKeys, with touch required. Preserve slot 1; keep helpers, confirmations, tests, and upstream CLI examples consistent.

- `secrets/wrapped` is the private `simlun-ai/homelab-wrapped-secrets` Git submodule; never commit ciphertext directly to the parent repository.
- Its `homelab_secrets/` Python project owns shared record cryptography, read-only token access, dependency pins, and `homelab-wrap`/`homelab-unwrap`. Parent helpers import it; keep programming and application-specific delivery in the parent. Preserve record-format compatibility when refactoring.
- Keep the public manifest at `secrets/manifest.json`, with paths relative to `secrets/`; do not add checksums. Public SSH keys remain in the parent repository.
- Require an initialized private submodule before generating or recovering credentials. Recovery USBs need complete, non-shallow clones of both repositories and the pinned submodule checkout.

## Before completing a change

1. Re-read the changed sections and the corresponding sections of related files.
2. Verify headings, names, quantities, storage topology, and references agree across documents.
3. Recalculate affected inventory totals and check the assumptions stated alongside them.
4. Ensure no unrelated information was removed and no planned item was incorrectly labeled deployed.
5. Summarize the changes and any remaining uncertainties.


