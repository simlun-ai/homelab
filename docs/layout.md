# Repository Layout

**Draft structure and operating conventions.** Proposed paths are repository-relative; they do not establish implementation or deployment.

## Document ownership

| Document | Authoritative content |
| --- | --- |
| [Inventory](inventory.md) | Hardware, node/disk assignments, shared equipment, capacity totals. |
| [Clusters](clusters.md) | Topology, dependencies, services, networking, workload and replica placement. |
| [Components](components.md) | Software catalog and versions; operational pins remain scope-owned. |
| This document | Directory ownership, tool scopes, provisioning boundaries, operating entry points. |
| [Installation](installation/README.md) | Main implementation TODO list, numbered installation runbooks, and verification progress. |
| [Security](security/security.md) | Core secrets, YubiKeys, custody, workstation handling, encryption. |
| [YubiKey catalogue](security/yubikey.md) | Credential/use-case catalogue, lookup identifiers, challenge construction, unresolved bootstrap coverage. |
| [Security work areas](security/security.md#remaining-decisions) | Topic documents under `docs/security/`, recording approved decisions and remaining TBD work. |
| [Backup and restore](backup-and-restore.md) | Backup design, independent recovery dependencies, restore planning. |
| [Emergency Recovery Guide](emergency-recovery-guide.md) | Standalone, non-secret USB recovery instructions. |

Keep details in their owning document and link from other documents. The USB guide must retain enough recovery instructions to work independently.

## Proposed root layout

| Path | Responsibility |
| --- | --- |
| `/README.md` | Brief overview, dependency order, and links to cluster READMEs, docs, and runbooks. |
| `/AGENTS.md` | Repository editing rules. |
| `/Makefile` | Help and explicit dispatch to one cluster or supporting-host scope. |
| `/.gitignore` | Downloaded tools and non-secret caches; subject to [secret-handling rules](security/security.md#secret-handling-boundary). |
| `/pyproject.toml` | Shared Python helper package/development configuration; locking format TBD. |
| `/docs/` | Documents listed above. |
| `/docs/installation/` | Installation plan and `NN-<headline>.md` runbooks; grow implementation as each step is tried. |
| `/secrets/manifest.json` | Public credential catalogue; no secrets or checksums. |
| `/secrets/wrapped/` | Private `homelab-wrapped-secrets` Git submodule containing authenticated encrypted records and the `homelab_secrets/` Python project; [storage policy](security/encrypted-record-storage.md). |
| `/clusters/{vault,backup,pi,metal}/` | Independent cluster configuration and operational pins. |
| `/make/` | Shared Make implementation, without global cluster-version defaults. |
| `/scripts/` | Python helpers and small Bash scripts. |
| `/charts/` | Repository-owned Helm source where useful. |
| `/tofu/modules/` | Reusable modules; live roots/state stay with their scopes. |
| `/support/ups/` | Shutdown-coordinator management and Vault bootstrap KMS configuration. |
| `/support/yubikey/` | Token setup scope; system installer, Python requirements, virtualenv, and Make entry points for step 00. |
| `/runbooks/` | Reusable supporting-host setup, ongoing operation, maintenance, and recovery procedures. |

## Common cluster layout

Every cluster follows this contract; optional directories appear only where needed.

| Path under `/clusters/<cluster>/` | Contents |
| --- | --- |
| `README.md` | Purpose, operational entry points, and links to architecture, inventory, and runbooks. |
| `Makefile` | Fixed cluster identity; shared rules loaded through absolute repository paths. |
| `toolchain.yaml` | Exact CLI/runtime versions, sources, checksums, supported operator platforms. |
| `bin/` | Ignored, reproducible tools and generated launchers. |
| `versions.yaml` | Talos, Kubernetes, extensions/images; schema TBD. |
| `cluster.yaml` | Non-secret settings, endpoint references, dependencies. |
| `nodes/` | Per-node role, hardware reference, addresses, explicit disk assignments. |
| `talos/patches/` | Non-secret cluster, role, and node patches. |
| `talos/image/` | Image Factory schematics or equivalent definitions/extensions. |
| `network/` | Interface assignments and network settings. |
| `storage/piraeus/` | Pool assignments, replica placement, StorageClasses where applicable. |
| `storage/manual/` | Manual-pool ownership/use records; no automatic creation or destruction. |
| `helm/releases.yaml` | Chart sources, exact versions, namespaces, values paths. |
| `helm/values/{infrastructure,workloads}/` | Cluster-owned release values. |
| `manifests/` | Resources outside Helm releases; secret references only. |
| `tofu/` | Independent OpenTofu root/state boundary; split further only for distinct lifecycles. |
| `tofu/.terraform.lock.hcl` | Committed provider lock. |

Keep machine-readable node assignments synchronized with the inventory. A declaration does not authorize disk initialization.

Plaintext secret-bearing kubeconfigs, talosconfigs, machine secrets, rendered configuration, tokens, and keys have no workstation-disk location. Wrapped credential records are permitted in `/secrets/wrapped/`. The required runtime workspace remains TBD under [security.md](security/security.md#secret-handling-boundary).

## Shared implementation

| Proposed path | Responsibility |
| --- | --- |
| `/make/common.mk` | Paths, scope checks, help, prerequisites. |
| `/make/tools.mk` | Install/verify scope pins. |
| `/make/talos.mk` | Render, bootstrap, operate, upgrade nodes through supported Talos APIs/integrations. |
| `/make/helm.mk` | Render/deploy selected releases. |
| `/make/tofu.mk` | Operate the selected root/state. |
| `/make/storage.mk` | Validate disks, coordinate assigned Piraeus preparation, inspect manual pools. |
| `/scripts/homelab/` | Token programming/verification and application consumers; shared wrapping/token access is imported from the private `homelab_secrets` project. Workstation unseal, [Talos KMS adapter](security/security.md#talos-kms-adapter), and [Vault bootstrap KMS](security/security.md#vault-bootstrap-kms) remain planned. |
| `/scripts/bash/` | Small shell helpers. |
| `/charts/<chart>/` | Chart definition, values, templates, dependency locks. |
| `/tofu/modules/<module>/` | Shared definitions without credentials or ownership of other scopes' state. |

Make supplies scope and resolved tools; helpers must not infer cluster, endpoint, version, or executable from ambient defaults. Use Python for substantial logic and Bash for small tasks. Helpers run on a workstation or suitable runner; Ansible base bootstrap is implemented for UPS hosts; service configuration and hardware verification remain pending.

Reference upstream charts by version rather than copying them. Package repository-owned charts as immutable versioned artifacts so clusters can adopt changes separately; artifact source and release orchestration remain TBD.

## Tool versions and command scopes

Each cluster scope owns `toolchain.yaml` and `bin/`. Cluster pins cover `kubectl`, `talosctl`, `helm`, `tofu`, and required clients/runtimes such as `bao` or Python. Select tools for the operator's OS/architecture, independently of node architecture.

Make verifies pins, uses absolute executable paths, and prepends the scope's `bin/` to subprocess `PATH`. Missing/mismatched tools fail or trigger pinned installation; never fall back to global tools. Document/check bootstrap Make and helper-runtime prerequisites.

The first implemented scope is `support/yubikey/`: an idempotent script installs system dependencies, and standard `venv`/`pip` installs the pinned build tooling and the local private `secrets/wrapped/homelab_secrets` project into its ignored `.venv/`. The private project's `pyproject.toml` owns token/crypto pins and installs `homelab-wrap` and `homelab-unwrap`. Make invokes that virtualenv's Python directly. See [step 00](installation/00-yubikey-setup.md) for preparation/install commands.

Illustrative targets, not yet implemented:

```sh
make help
make CLUSTER=vault tools
make CLUSTER=vault bootstrap
make -C clusters/vault status
make -C clusters/pi node-bootstrap NODE='<node-id>'
make -C clusters/metal upgrade
```

Root dispatch and direct invocation resolve the same scope. Default to help; mutating targets require one explicit scope, with no default all-cluster mutation. Resolve endpoints/credentials independently of the current Kubernetes context.

CLI, Talos/Kubernetes, and Helm pins each have one authoritative location. Validate compatibility during upgrades; shared helpers must support clusters still using older pins. Catalog changes do not upgrade clusters.

## Provisioning and storage ownership

Aim for unattended, repeatable provisioning once prerequisites, identities, disk assignments, and secret access are established. Validate inputs before mutation and stop on ambiguity.

| Storage category | Boundary |
| --- | --- |
| Assigned Talos OS disks | Automate installation and supported mirror/encryption setup after validation. |
| Assigned Piraeus disks | Automated preparation may use only declared devices; pool/encryption implementation TBD. |
| Non-Piraeus ZFS data disks | Manual preparation/repair only; no automatic wipe, format, create, replace, or destroy. |
| Other data disks, spares, unknown devices | Excluded until explicitly assigned. |

Use stable disk identities and validate mappings, especially through USB adapters or replacement. Never select by size, apparent emptiness, or `/dev/sdX` alone. Distinguish new provisioning from rebuilds; existing signatures require review, not automatic wiping.

The inventory identifies protected storage: Vault/Backup data mirrors, Metal's non-`piraeus` ZFS pools, old NAS storage, and worker3's separate `ethereum` XFS filesystem.

Manual-pool declarations may drive non-destructive checks/integration. Import, unlock, mounting, or volume provisioning need separately defined automation; missing/unexpected storage is an error, never grounds to recreate a pool. Destructive maintenance belongs in manual runbooks. Encryption requirements belong in [security.md](security/security.md#disk-encryption-and-opentofu).

## UPS shutdown coordinators

Use one `/support/ups/` scope for Ansible provisioning and ongoing management of all UPS coordinators. Base bootstrap, hardening, and verification are implemented; KMS, NUT, and exporters remain pending. `ups-aux` serves both Vault and Backup. Hardware, power supplies, and UPS mappings belong in the inventory.

| Path under `/support/ups/` | Contents |
| --- | --- |
| `README.md` | Operational entry points and links to mappings/recovery. |
| `Makefile` | Implemented local tools/inventory/syntax targets and single-host bootstrap/hardening/verification. |
| `requirements.txt` and `.venv/` | Implemented Ansible dependency pins and ignored tools, invoked explicitly as in the YubiKey scope. |
| `install-system-dependencies.sh`, `check-tools.py` | Ubuntu 26.04 workstation prerequisites and runtime/dependency verification. |
| `inventory.yaml`, `ansible.cfg` | Three approved hostnames, `administrator` SSH account, and strict SSH settings; IP addresses TBD. |
| `ansible/playbooks/`, `ansible/tasks/`, `ansible/files/` | Implemented single-host bootstrap, sudo policy, and verification. |
| `ansible/roles/` | Implemented `coordinator_hardening`; shutdown-manager/service roles remain planned. |
| `ansible/templates/` | Non-secret service templates. |
| `ansible/requirements.yml` | Pinned external roles/collections if selected. |

Raspberry Pi OS Lite (64-bit) on microSD is selected. The shared [base setup runbook](../runbooks/ups-coordinator-base-setup.md) covers image preparation from a Linux workstation and Ansible bootstrap for all three coordinators. [01 - Main coordinator](installation/01-main-coordinator.md) adds Vault's bootstrap KMS services. The Vault/Backup coordinator also hosts the planned [Vault bootstrap KMS](security/security.md#vault-bootstrap-kms); keep its non-secret configuration in this supporting-host scope. Deploy its [wrapped credentials](security/encrypted-record-storage.md#coordinator-deployment) to local persistent storage; Ansible copies ciphertext without decrypting it. OpenTofu has no assigned coordinator role. NUT and Prometheus exporter setup will be added to the shared runbook later; shutdown credentials, triggers, and sequencing remain TBD; apply the [secret-handling policy](security/security.md#secret-handling-boundary).

### Power-loss shutdown and manual startup

**Decision:** After UPS-triggered shutdown, systems remain off until the operator powers them on one at a time, even if mains power returns during shutdown.

- Set firmware power restoration to **stay off**; disable Wake-on-LAN and other automatic wake sources where supported. No scheduled or coordinator-driven power-on.
- Record device support, settings, and verification in the inventory. Check Raspberry Pi boards, coordinators, and UPS outlets separately; unsupported behavior/manual power isolation remain TBD.
- Bring Vault services up before dependent clusters. Exact node order/readiness checks belong in the startup runbook.
- Manual disk unlock and OpenBao unseal are acceptable under the independent-recovery design.
- This policy permits explicitly requested maintenance reboots and unattended provisioning after deliberate power-on.

These are intended settings, not verified hardware behavior.

## Central runbooks

Each runbook states scope, prerequisites, secret-source references, expected state, ordered steps, verification, and recovery actions. Link scope-specific inputs rather than copying procedures.

Numbered installation procedures and their implementation progress belong in [docs/installation/](installation/README.md), beginning with YubiKeys, the main coordinator, and Vault. Add dependent-cluster installation steps there as work progresses. Shared supporting-host setup lives in `/runbooks/` and is linked from numbered installation steps. The operating runbooks below should reuse those procedures where applicable.

| Proposed path under `/runbooks/` | Procedure |
| --- | --- |
| `README.md` | Index/conventions. |
| [`ups-coordinator-base-setup.md`](../runbooks/ups-coordinator-base-setup.md) | Shared OS installation and implemented Ansible base bootstrap; hardware verification pending. |
| `bootstrap-node.md` | Add/rebuild without touching protected data. |
| `upgrade-cluster.md` | Upgrade tools/components, verify health, record recovery options. |
| `prepare-manual-zfs-pool.md` | Identify/prepare encrypted manual storage. |
| `replace-zfs-mirror-member.md` | Replace deliberately; verify resilvering. |
| `replace-md-raid1-os-disk.md` | Replace OS member; restore bootability and verify. |
| `recover-piraeus-volume.md` | Recover replicas/placement after failure or maintenance. |
| `recover-encryption-access.md` | Recover/rotate unlock access under [security.md](security/security.md). |
| `unseal-openbao.md` | Workstation/YubiKey unseal with memory-only secret handling. |
| `operate-talos-kms.md` | Deploy/verify the adapter, rotate transit keys, and recover dependent-node unlock. |
| `operate-vault-bootstrap-kms.md` | Operate/recover the coordinator KMS, touch-authorized sessions, DNS-01 renewal, time readiness, and network hardening; initial setup belongs in [01 - Main coordinator](installation/01-main-coordinator.md). |
| `restore-openbao.md` | Implement/test [snapshot recovery to a replacement Pi 4 or memory-backed workstation container](backup-and-restore.md#required-recovery-targets). |
| `ups-shutdown-and-startup.md` | Verify shutdown, stay-off behavior, manual dependency-ordered startup. |

## Open decisions

- Talos MD RAID1 installation and boot recovery on each platform.
- Node/disk schema and inventory synchronization.
- Helm orchestration, immutable-chart storage, and scripts/OpenTofu division.
- Scope-specific architecture questions remain in [clusters.md](clusters.md); security and backup implementation questions remain in their owning documents.


