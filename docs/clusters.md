# Clusters

The target design uses one monorepo for four Talos Linux Kubernetes clusters. The following describes intended architecture, not verified deployment status. See [layout.md](layout.md) for the draft repository structure and unresolved implementation details.

Common goals:

- Independently pinned tools and component versions for each cluster, with Makefiles selecting tools from that cluster's `bin/` directory.
- Unattended provisioning where possible, limited to explicitly assigned OS and Piraeus disks. Non-Piraeus ZFS data pools are prepared and repaired manually.
- Encryption for all ZFS storage; OS disk encryption is also a goal. Key delivery, a possible shared disk-unlock key, and recovery remain TBD.
- Core secrets rely on the four matching, touch-required HMAC-SHA1 YubiKeys and a separately held offline golden key. No secrets are committed or written to workstation disk; encrypted service storage and backups are allowed. See [security.md](security.md) and [backup-and-restore.md](backup-and-restore.md).
- Selected infrastructure workloads, such as monitoring, may run on control-plane nodes. Application workloads belong on workers where workers exist; exact scheduling controls are TBD.
- After a UPS-triggered shutdown, systems remain off for operator-controlled startup, one machine at a time. Disable power-on after power restoration, Wake-on-LAN, and other automatic wake sources where supported. Bring Vault services up before dependent clusters; detailed sequencing and per-device verification remain TBD in [layout.md](layout.md#power-loss-shutdown-and-manual-startup).
- Three separate shutdown coordinators serve Vault + Backup (Raspberry Pi 2), Pi (Raspberry Pi 3), and Metal (Raspberry Pi 3). Raspberry Pi OS Lite and Ansible are tentative choices for these supporting hosts.

## Vault

The Vault cluster is the foundational cluster: it does not depend on any of the other clusters, while all other clusters depend on services it provides. To avoid circular dependencies, the Vault cluster's own secrets are entered manually rather than retrieved from OpenBao. Manual entry must follow the workstation no-disk rule; bootstrap, disk unlock, and recovery must work without its own OpenBao instance or another cluster.

### Platform and networking

- Single-node Talos Kubernetes cluster.
- Flannel for pod networking (no Cilium).
- MetalLB for LoadBalancer services.
- Traefik for ingress.
- Headlamp for Kubernetes management.

### Storage and backups

- **OS:** 2 × 128 GB Intenso USB SSDs in MD RAID1 (128 GB nominal usable).
- **Storage:** The other 2 × 128 GB Intenso USB SSDs in a ZFS mirror (128 GB nominal usable).
- The data mirror is manually prepared and must be encrypted; exact encryption and unlock implementation are TBD.
- zfs-localpv for local persistent volumes.
- OpenBao uses integrated Raft storage with scheduled online snapshots uploaded to Cloudflare R2 by a job inside Vault. Detailed backup and recovery requirements belong in [backup-and-restore.md](backup-and-restore.md#openbao-online-backups).

### Monitoring and alerting

- kube-prometheus-stack (Prometheus, Grafana, and Alertmanager).
- Alertmanager notifications via Telegram.

### Secrets and certificates

- OpenBao provides centralized secrets management for dependent clusters; the Vault cluster does not rely on it for its own secrets.
- The core-secret foundation is the shared, touch-required YubiKey HMAC-SHA1 design in [security.md](security.md#core-secret-foundation). Exact disk-unlock and OpenBao unseal-material wrapping are planned, not yet implemented. The [Emergency Recovery Guide](emergency-recovery-guide.md) accompanies each token at its separate location.
- cert-manager issues Let's Encrypt certificates using Cloudflare DNS-01 validation.
- External Secrets Operator uses PushSecret to publish cert-manager certificates to OpenBao.
- Dependent clusters use External Secrets Operator connected to OpenBao to pull certificates.

## Backup

Planned Talos cluster on the Lenovo ThinkCentre M93p Tiny described in [inventory.md](inventory.md#backup).

- Intel 180 GB SSD for the OS.
- Manually prepared ZFS mirror using two 8 TB Samsung USB HDDs; encryption is required.
- Depends on Vault services. Workloads, backup software, retention, and storage integration are TBD.

## Shared infrastructure

Shared exclusively by the **Vault and Backup clusters**:

- **UPS:** 1 × Eaton 3S700 supplying power to both clusters.
- **Shutdown coordinator:** 1 × Raspberry Pi 2, connected to this UPS via USB for monitoring and safe shutdown of both Vault and Backup. Powered from the Eaton 3S700's 2 A USB power outlet. This supporting host is separate from their Talos nodes.

## Pi

- Five active Raspberry Pi 4 nodes: three control-plane nodes and two workers, plus one cold spare.
- Talos Linux on every active node, with an MD RAID1 OS pair and one Piraeus data SSD per node.
- Proposed Piraeus data plane spans control-plane and worker nodes, likely using Placement Count 2 and separate StorageClasses preferring infrastructure or worker data placement. Pool details, encryption, quorum, and placement rules remain TBD; see [layout.md](layout.md#workload-and-piraeus-placement).
- One Raspberry Pi 3 coordinates shutdown via the Eaton UPS, separately from the Talos cluster.

## Metal

- Talos Linux on three active control-plane nodes and four workers; one M920x is a cold spare.
- Preserve the MD RAID1 OS disks and the single-disk or mirrored `piraeus` pools recorded in [inventory.md](inventory.md#metal).
- Proposed Piraeus data plane spans control-plane and worker nodes, likely using Placement Count 2. Separate StorageClasses should prefer data placement within each role group, with diskless quorum participants/tiebreakers allowed across the boundary. Exact behavior remains TBD.
- Non-Piraeus ZFS pools are manually prepared and protected from automatic provisioning. All ZFS storage requires encryption; the `ethereum` XFS filesystem remains separate from Piraeus.
- Dedicate the 2.5 Gbit/s interfaces to Piraeus/DRBD data. Two five-port switches are available; one for control-plane nodes and one for workers, with a possible inter-switch link, is the tentative topology. Addresses and final cabling are TBD.
- One Raspberry Pi 3 coordinates shutdown for the cluster's three Eaton UPS units, separately from the Talos cluster.
