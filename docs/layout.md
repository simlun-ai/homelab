# Repository Layout

**Status: initial draft.** This document proposes the directory layout and operating conventions for the homelab monorepo. It will be refined in small steps. Paths below are proposed; documenting them does not create the directories or establish that anything is configured or deployed.

One repository manages four Talos Linux Kubernetes clusters, in this order: **Vault**, **Backup**, **Pi**, **Metal**. Raspberry Pi UPS shutdown coordinators are supporting hosts, separate from the Kubernetes clusters.

## Design goals

- Upgrade and operate one cluster at a time, with independently pinned tools and component versions.
- Keep each cluster's tools under its own `bin/` directory and select them through Makefiles.
- Use Makefiles for entry points, Python for substantial helper logic, Bash for suitable small tasks, Helm for Kubernetes releases, and OpenTofu where declarative resource management fits.
- Never commit secrets or let secrets touch the workstation's disk, including the checkout, temporary files, and tool caches. Encrypted persistence in cluster services and backups is allowed.
- Encrypt all ZFS storage. Aim to encrypt OS disks as well. A shared disk-unlock key or passphrase is an acceptable option to investigate for simplicity.
- Make provisioning as unattended, scripted, and repeatable as possible, within explicitly assigned disk boundaries.
- Prepare all non-Piraeus ZFS data disks and pools manually. Provisioning must preserve them through installation, upgrades, rebuilds, and removal of nodes.
- Allow infrastructure workloads, such as monitoring, on control-plane nodes; keep application workloads on workers where workers exist.
- Document common operations centrally in `/runbooks/`, with a brief root README and more detailed cluster READMEs.

## Proposed root layout

Paths beginning with `/` are relative to the repository root, not the host filesystem.

| Path | Responsibility |
| --- | --- |
| `/README.md` | Brief cluster overview, dependency order, links to cluster READMEs, documentation, and runbooks. |
| `/AGENTS.md` | Repository editing rules and invariants. |
| `/Makefile` | Discoverable entry points and explicit dispatch to one cluster or supporting-host scope. |
| `/.gitignore` | Exclude downloaded tools and non-secret caches; never use this as permission to write secrets to the workstation. |
| `/pyproject.toml` | Shared Python helper package and development configuration; dependency locking format TBD. |
| `/docs/inventory.md` | Physical hardware, disk ownership, pool names, network equipment, and capacity accounting. |
| `/docs/clusters.md` | Cluster architecture, topology, dependencies, and services. |
| `/docs/components.md` | Component catalog; exact operational pins belong to the relevant cluster. |
| `/docs/layout.md` | This draft: directory ownership, operating conventions, and unresolved decisions. |
| `/clusters/vault/` | Independent foundational cluster. |
| `/clusters/backup/` | Backup cluster. |
| `/clusters/pi/` | Raspberry Pi Kubernetes cluster. |
| `/clusters/metal/` | Metal Kubernetes cluster. |
| `/make/` | Shared Make includes; implementation only, without global cluster-version defaults. |
| `/scripts/` | Shared Python helpers and suitable Bash scripts. |
| `/charts/` | Repository-owned Helm chart source, added only where useful. |
| `/tofu/modules/` | Reusable OpenTofu modules; live roots and state ownership stay with their scopes. |
| `/support/ups/` | Configuration and management of the three Raspberry Pi shutdown coordinators. |
| `/runbooks/` | Common bootstrap, maintenance, recovery, and shutdown procedures. |

The initial change creates this document and aligns related documentation. The proposed implementation tree will be built incrementally.

## Common cluster layout

Every directory under `/clusters/` follows the same contract. `<cluster>` means `vault`, `backup`, `pi`, or `metal`; optional subdirectories appear only when the cluster needs them.

| Path under `/clusters/<cluster>/` | Contents |
| --- | --- |
| `README.md` | Purpose, topology, dependencies, operational entry points, and links to inventory and runbooks. |
| `Makefile` | Fix this cluster's identity and load shared Make rules using absolute repository paths. |
| `toolchain.yaml` | Exact CLI/runtime versions, download sources, and checksums for supported operator platforms. |
| `bin/` | Downloaded tools and generated launchers for this cluster; Git-ignored and reproducible. |
| `versions.yaml` | Talos, Kubernetes, and Talos extension/image pins; schema TBD. |
| `cluster.yaml` | Non-secret cluster settings, endpoint references, and dependency declarations. |
| `nodes/` | One non-secret file per node: role, hardware reference, addresses, and explicitly assigned disks. |
| `talos/patches/` | Non-secret cluster-wide, role, and node patches. |
| `talos/image/` | Image Factory schematics or equivalent image definitions, including required extensions. |
| `network/` | Interface assignments and intended network configuration; unknown addresses stay TBD. |
| `storage/piraeus/` | Piraeus pool assignments, replica-placement intent, and StorageClass definitions, where applicable. |
| `storage/manual/` | Records of manually prepared pools and their intended use; no automatic creation, formatting, or destruction. |
| `helm/releases.yaml` | Explicit release list with chart sources, exact chart versions, namespaces, and values paths. |
| `helm/values/infrastructure/` | Cluster-owned values for infrastructure releases. |
| `helm/values/workloads/` | Cluster-owned values for application releases, where applicable. |
| `manifests/` | Cluster-owned Kubernetes resources that do not fit a Helm release; references to secrets only. |
| `tofu/` | Independent OpenTofu root for this cluster, split further only when lifecycles justify it. |
| `tofu/.terraform.lock.hcl` | Committed provider dependency lock file for this root. |

`nodes/` records machine-readable assignments, while `docs/inventory.md` remains the human-readable hardware inventory. Changes must keep them synchronized. A pool declaration records ownership and intent; it does not itself grant permission to initialize disks.

There is deliberately no proposed workstation-disk location for kubeconfigs, talosconfigs, generated machine secrets, rendered secret-bearing configuration, tokens, or disk keys. A runtime workspace for tools requiring paths is TBD and must be memory-only.

## Shared implementation

| Proposed path | Responsibility |
| --- | --- |
| `/make/common.mk` | Repository paths, scope checks, help, and common prerequisites. |
| `/make/tools.mk` | Install and verify the selected scope's pinned tools. |
| `/make/talos.mk` | Talos rendering, bootstrap, node operations, and upgrades. |
| `/make/helm.mk` | Render and deploy the selected cluster's releases. |
| `/make/tofu.mk` | Operate only the selected OpenTofu root and its state. |
| `/make/storage.mk` | Validate disk assignments and coordinate approved Piraeus preparation; inspect manual pools. |
| `/scripts/homelab/` | Python modules for tool installation, configuration validation, secret transport, and operation orchestration. |
| `/scripts/bash/` | Small shell helpers where Bash is the clearer implementation. |
| `/charts/<chart>/` | `Chart.yaml`, `values.yaml`, `templates/`, and dependency locks for repository-owned charts. |
| `/tofu/modules/<module>/` | Shared resource definitions without embedded credentials or ownership of other clusters' state. |

Shared code receives the scope and resolved tool paths from Make. It must not choose a cluster, endpoint, version, or executable from ambient shell defaults. Substantial logic belongs in Python rather than growing into complex Make recipes.

Helpers run on the workstation or an appropriate automation runner. Talos node operations use the Talos API and supported integrations; the proposed Ansible scope is the Raspberry Pi OS shutdown coordinators.

Upstream charts are referenced by version instead of copied into the repository. Repository-owned charts should be packaged as immutable versioned artifacts before use, so each cluster can adopt a chart change separately. The artifact source is TBD.

## Tool versions and command scopes

`toolchain.yaml` is independent for every cluster. It covers at least `kubectl`, `talosctl`, `helm`, and `tofu`, plus other required clients and runtimes such as `bao` or Python when needed. Tools are selected for the operator machine's OS and architecture, independently of the managed nodes' architecture.

The cluster Makefile resolves its own `bin/`, verifies tools against the pins, and uses absolute executable paths. It prepends that directory to subprocess `PATH` for tools that invoke other tools. A missing or mismatched tool must fail or trigger the pinned installation step; it must never silently fall back to a global installation. Bootstrap prerequisites such as Make and the initial helper runtime must be documented and checked.

Illustrative interface; these targets do not exist yet:

```sh
make help
make CLUSTER=vault tools
make CLUSTER=vault bootstrap
make -C clusters/vault status
make -C clusters/pi node-bootstrap NODE='<node-id>'
make -C clusters/metal upgrade
```

Root dispatch and direct cluster invocation must resolve the same scope. The default target is help. Mutating targets require one explicit scope; there is no default command that applies changes to all four clusters. Endpoint and credential selection follow the scope, independently of the user's current Kubernetes context.

CLI pins, Talos/Kubernetes pins, and Helm chart pins serve different purposes. Keep each version in one authoritative location and validate compatibility during an upgrade. Shared helpers must continue to support the pins of clusters that have not yet upgraded. Changing a component-catalog entry does not upgrade a cluster.

## Secrets, state, and disk encryption

### Secrets handling

The hard rule is **no secrets in Git and no secrets written to the workstation's disk**, including the checkout, temporary files, ignored files, cached credentials, logs, shell history, crash dumps, and persisted plans. Secret references and non-secret templates may be committed.

The delivery mechanism is TBD: an external secrets manager or OpenBao in the Vault cluster are candidates. SOPS with age remains a last-resort candidate to evaluate, with Git storage of encrypted payloads still undecided. Decryption must never materialize secrets on the workstation's disk, and private age keys must follow the same handling rule.

Prefer direct API calls, process memory, and streams when implementing secret transport. Tools that require file paths need a verified memory-only mechanism with workstation swap, hibernation, dumps, caches, and failure paths accounted for. An ignored directory or a temporary file deleted afterward does not satisfy the rule.

The workstation restriction does not prohibit encrypted persistence in cluster services or backups. OpenBao's encrypted backend, Kubernetes Secrets in etcd with appropriate encryption at rest, protected Talos node state, and encrypted backups fit that boundary. Their encryption and key-management details still need implementation and verification. Secret transport and backup/restore operations must not stage sensitive contents on workstation disk.

Vault's own secrets remain manually supplied without relying on its OpenBao instance. Its disk unlock, OpenBao unseal/recovery, and restore credentials must also be available without any other cluster. Manual input still follows the workstation no-disk rule. The recovery source and unattended-unlock mechanism are TBD.

### OpenTofu state

Each cluster owns its own state boundary; there is no shared state covering all four clusters. Supporting hosts or external resources get separate state only if OpenTofu actually manages them.

State backend, locking, encryption, and recovery are TBD. Encrypted remote state is allowed; secret-bearing state and saved plans must never be written to workstation disk. Marking a value `sensitive` or choosing a remote backend does not by itself prevent local writes. Review provider behavior, local working data, error recovery files, and logs before using a resource that handles secrets. Any secret-bearing local runtime data must remain memory-only, including during failures.

The Vault bootstrap path must not require a state backend or an encryption-key service that only becomes available after Vault is running.

### Encryption intent

- **All ZFS pools:** encryption is required, including Piraeus backing storage and manually prepared pools. If native ZFS encryption is selected, express this through encrypted datasets and zvols with verified inheritance; native encryption is not blanket encryption of all pool metadata. The exact layer and provisioning sequence remain TBD.
- **OS disks:** encryption is a goal. Validate it alongside the planned MD RAID1 layout and each hardware platform. Talos system-volume encryption must not be described as proof that every boot partition is encrypted. Its static `STATE` key option stores key material in `META`; select a key method that provides the intended disk protection.
- **Shared key:** a shared disk-unlock key or passphrase may simplify operation. Exact key formats, delivery, rotation, recovery, and compatibility across ZFS and Talos remain TBD. Do not assume their internal encryption keys are interchangeable.
- **Boot and recovery:** avoid requiring a key service hosted on the very storage being unlocked. Vault must be recoverable independently; other clusters need a defined recovery path when Vault is unavailable.

Encryption here is desired configuration, not a claim about the current disks. Existing-data migration must be planned explicitly and must preserve the manual-storage boundary.

## Provisioning and storage ownership

Automation should proceed unattended after prerequisites, identities, disk assignments, and secret access have been established. Each operation validates those inputs before it changes a node and stops on ambiguity.

| Storage category | Provisioning boundary |
| --- | --- |
| Assigned Talos OS disks | Automate installation and supported mirror/encryption setup once validated. Match explicit disk identities and expected state. |
| Assigned Piraeus data disks | Candidates for automated preparation, limited to the node's declared Piraeus devices. Exact pool and encryption implementation TBD. |
| Non-Piraeus ZFS data disks | Manual preparation and repair only. No automatic wipe, format, pool creation, replacement, or destruction. |
| Other data disks, spares, and unknown devices | Excluded from provisioning unless their role is explicitly decided and recorded. |

Never select disks merely because they are empty, unused, large, or currently appear under a particular `/dev/sdX` name. Record stable device identifiers and validate their mapping; USB adapters and replacement drives need particular care. Initial provisioning and rebuilding an existing node are distinct operations. Existing signatures must cause a stop for review, not an automatic wipe.

Manual pools include Vault's data mirror, Backup's data mirror, and Metal's `immich`, `photos`, `media`, `dump`, `nas`, `bitcoin`, and `nvr` pools. The old NAS ZFS storage is also outside cluster provisioning. Metal worker3's XFS filesystem `ethereum` is separate from Piraeus and remains outside automated preparation.

Once a manual pool has been prepared, its declaration can support non-destructive checks and integration. Any automated import, unlock, mounting, or volume provisioning must be separately defined and must never recreate a missing pool. Missing or unexpected storage is an error. Destructive maintenance belongs to the relevant manual runbook.

## Cluster scopes

### Vault

`/clusters/vault/` describes the independent single-node Talos cluster. Preserve Flannel, MetalLB, Traefik, kube-prometheus-stack with Telegram alerting, Headlamp, cert-manager, External Secrets Operator, OpenBao, and ZFS LocalPV as documented in [clusters.md](clusters.md#vault).

Keep the MD RAID1 OS pair separate from the manually prepared ZFS data mirror. Preserve Cloudflare DNS-01 certificate issuance, PushSecret publication to OpenBao, and encrypted Cloudflare R2 backups including the OpenBao PVC, without staging secrets on workstation disk. Vault has no Piraeus directory unless its design is explicitly changed.

### Backup

`/clusters/backup/` describes the Talos cluster on the Lenovo M93p Tiny. Its 180 GB OS SSD and manual 8 TB mirror remain distinct. Workloads, backup software, schedules, retention, and storage integration are TBD. Do not assume the presence of a component in the catalog assigns it to Backup.

### Pi

`/clusters/pi/` describes three control-plane nodes and two workers, with the cold spare recorded separately. Each active node has an MD RAID1 OS pair and one Piraeus data SSD. Infrastructure may run on the control plane; application workloads belong on the workers. The Piraeus design below applies as a proposal, with the backing-pool details still TBD.

### Metal

`/clusters/metal/` describes three active control-plane nodes and four workers, with the M920x cold spare recorded separately. Preserve the existing OS mirrors, single-disk or mirrored `piraeus` pools, manual application pools, and `ethereum` filesystem from [inventory.md](inventory.md#metal).

Use `network/` to record the dedicated 2.5 Gbit/s Piraeus/DRBD data network. The two available five-port switches are tentatively split between control-plane nodes and workers, with a possible inter-switch link. Addresses, subnets, routing, MTU, and final cabling are TBD. Keep management and ordinary application traffic off these dedicated interfaces.

## Workload and Piraeus placement

Control-plane nodes are intended to carry selected infrastructure workloads, including monitoring. Scheduling configuration must preserve capacity for control-plane services and prevent general application workloads from landing there. Exact Talos settings, labels, taints, tolerations, and resource reservations are TBD; enabling control-plane scheduling alone is not the complete policy. Single-node clusters need a policy appropriate to their documented purpose.

For Pi and Metal, favor maintainability and propose one Piraeus data plane per cluster spanning control-plane and worker nodes. These are separate cluster data planes, not cross-cluster replication.

| Proposed StorageClass | Data-placement preference |
| --- | --- |
| `piraeus-infrastructure` | Prefer diskful data replicas on control-plane nodes. |
| `piraeus-workloads` | Prefer diskful data replicas on worker nodes. |

Names are provisional. The likely default is **Placement Count 2**, meaning two diskful replicas per volume. Diskless quorum participants or tiebreakers may live across the control-plane/worker boundary and do not count as additional data copies. Replica placement and workload scheduling are separate policies.

Exact LINSTOR properties, preference versus strict constraints, fallback behavior, quorum/tiebreaker placement, and the encryption path remain TBD. Validate maintenance and failure behavior, including loss of a node, a switch, or the link between switches, before adopting the design. Two data replicas alone do not establish the desired availability guarantees.

## UPS shutdown coordinators

Use one supporting-host scope because one coordinator serves two clusters and should not have duplicate ownership.

| Path under `/support/ups/` | Contents |
| --- | --- |
| `README.md` | Coordinator roles, UPS mappings, shutdown order, and recovery links. |
| `Makefile` | Explicit coordinator-management targets. |
| `toolchain.yaml` and `bin/` | Independently pinned management tools and ignored local installations. |
| `inventory.yaml` | Three Raspberry Pi 3 hosts and the equipment each protects; identifiers and addresses TBD. |
| `ansible/playbooks/` | Proposed host configuration and update entry points. |
| `ansible/roles/` | Proposed shutdown-manager setup and service configuration. |
| `ansible/templates/` | Non-secret service templates. |
| `ansible/requirements.yml` | Pinned external collections or roles if Ansible is selected. |

The three coordinator roles are **Vault + Backup**, **Pi**, and **Metal**, matching the hardware inventory. Raspberry Pi OS Lite is the tentative OS; Ansible is the proposed configuration tool. Both remain choices to confirm. OpenTofu may manage suitable surrounding resources but has no assigned coordinator role yet. Shutdown software, credentials, triggering rules, and shutdown/startup sequencing are TBD. These hosts follow the same secret-handling requirements.

## Central runbooks

Runbooks should state scope, prerequisites, secret sources by reference, expected state, ordered steps, verification, and recovery actions. Keep common procedures here and link cluster-specific inputs instead of copying whole procedures into each README.

| Proposed path | Procedure |
| --- | --- |
| `/runbooks/README.md` | Index and conventions. |
| `/runbooks/bootstrap-vault.md` | Bootstrap or recover the independent foundation, including access to recovery material. |
| `/runbooks/bootstrap-cluster.md` | Bootstrap one dependent cluster. |
| `/runbooks/bootstrap-node.md` | Add or rebuild one node without touching protected data disks. |
| `/runbooks/upgrade-cluster.md` | Upgrade one cluster's tools and components, verify health, and document recovery options. |
| `/runbooks/prepare-manual-zfs-pool.md` | Manually identify and prepare encrypted non-Piraeus storage. |
| `/runbooks/replace-zfs-mirror-member.md` | Identify a failed member, replace it deliberately, and verify resilvering. |
| `/runbooks/replace-md-raid1-os-disk.md` | Replace an OS mirror member, restore bootability, and verify the mirror. |
| `/runbooks/recover-piraeus-volume.md` | Recover replicas or placement after a failure or maintenance event. |
| `/runbooks/recover-encryption-access.md` | Recover or rotate disk-unlock access without circular dependencies. |
| `/runbooks/restore-openbao.md` | Restore OpenBao and its independently held recovery material. |
| `/runbooks/ups-shutdown-and-startup.md` | Exercise shutdown coordination and restart in dependency order. |

## Open decisions for later iterations

1. Secret delivery and memory-only workstation runtime paths; whether a SOPS + age fallback is needed and how encrypted payloads would be stored.
2. OpenTofu remote state, encryption, failure handling, and independently accessible Vault recovery material.
3. Talos MD RAID1 installation, boot recovery, and OS encryption on each hardware platform.
4. ZFS encryption layer, shared-key strategy, key recovery, and unattended unlock without circular dependencies.
5. Node/disk configuration schema and how to keep machine-readable declarations synchronized with the inventory.
6. Piraeus pool preparation, StorageClass semantics, two-replica quorum behavior, and maintenance procedures.
7. Metal's dedicated storage-network addressing and physical switch topology.
8. Helm release orchestration, immutable chart storage, and exact division of work between scripts and OpenTofu.
9. Coordinator OS, configuration tool, shutdown software, and power-event sequencing.

## Upstream references

These references inform the unresolved implementation details; they do not establish that the proposed configuration is supported on every node or already deployed.

- [Talos disk encryption](https://docs.siderolabs.com/talos/v1.14/configure-your-talos-cluster/storage-and-disk-management/disk-encryption): system volumes, persisted node secrets, and key handling.
- [OpenZFS dataset properties](https://openzfs.github.io/openzfs-docs/man/master/7/zfsprops.7.html): encryption roots, datasets, and key delivery.
- [OpenZFS encryption behavior](https://openzfs.github.io/openzfs-docs/man/master/8/zfs-load-key.8.html#encryption): inheritance and metadata coverage.
- [Piraeus replicated volumes](https://piraeus.io/docs/stable/tutorial/replicated-volumes/): Placement Count and diskful replicas.
- [OpenTofu state and plan encryption](https://opentofu.org/docs/language/state/encryption/): persistence and encryption considerations.
- [Kubernetes Secrets](https://kubernetes.io/docs/concepts/configuration/secret/): etcd persistence and encryption considerations.
- [OpenBao security model](https://openbao.org/docs/internals/security/): encrypted storage and recovery considerations.
