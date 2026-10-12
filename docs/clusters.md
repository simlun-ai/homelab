# Clusters

**Planned architecture; deployment is unverified.** All four Kubernetes clusters target Talos Linux.

Hardware and disk assignments belong in [inventory.md](inventory.md); tool scopes and provisioning rules in [layout.md](layout.md); secret handling and encryption in [security.md](security.md).

## Vault

Independent, single-node foundation. All other clusters depend on its services. Its own secrets are supplied manually so bootstrap, disk unlock, and recovery do not depend on its OpenBao instance or another cluster.

| Function | Components |
| --- | --- |
| Networking | Flannel pod networking (no Cilium), MetalLB LoadBalancer services, Traefik ingress. |
| Management | Headlamp. |
| Storage | Local persistent volumes via ZFS LocalPV on the [Vault data mirror](inventory.md#vault), separate from the OS mirror. |
| Monitoring | kube-prometheus-stack (Prometheus, Grafana, Alertmanager), with Telegram notifications. |
| Secrets | OpenBao for application/service secrets and transit-backed disk-key wrapping; planned Python Talos KMS adapter. |
| Certificates | cert-manager with Let's Encrypt and Cloudflare DNS-01; External Secrets Operator PushSecret publishes certificates to OpenBao, and dependent clusters pull them through External Secrets Operator. |

Backup, Pi, and Metal depend on Vault's unsealed OpenBao and KMS adapter for [Talos system-volume unlock](security.md#talos-kms-adapter). Vault's own system-volume unlock uses the independent [YubiKey-backed coordinator KMS](security.md#vault-bootstrap-kms).

OpenBao storage, backups, and recovery are specified in [backup-and-restore.md](backup-and-restore.md#openbao-online-backups).

## Backup

Single-node cluster on the [Lenovo ThinkCentre M93p Tiny](inventory.md#backup), using its manually prepared ZFS mirror. Depends on Vault. Workloads, backup software, retention, and storage integration remain TBD.

## Shared infrastructure

Vault and Backup share the [UPS and shutdown coordinator](inventory.md#shared-infrastructure). The coordinator also hosts Vault's planned [bootstrap KMS](security.md#vault-bootstrap-kms).

## Pi

Three control-plane nodes and two workers, with a separate cold spare. Each active node has an OS mirror and a Piraeus data SSD; see [disk allocation](inventory.md#ssd-allocation).

## Metal

Three control-plane nodes and four workers, with a separate M920x cold spare. Piraeus uses the single-disk or mirrored `piraeus` pools in [inventory.md](inventory.md#metal). Other ZFS pools and the `ethereum` XFS filesystem remain outside automated preparation under the [storage ownership rules](layout.md#provisioning-and-storage-ownership).

### Dedicated storage network

Metal's 2.5 Gbit/s interfaces carry Piraeus/DRBD data only; management and ordinary application traffic use other interfaces. The tentative topology uses one switch for control-plane nodes and one for workers, with a possible inter-switch link. Switch hardware is listed in [inventory.md](inventory.md#dedicated-storage-network); cabling, addressing, subnets, routing, and MTU remain TBD.

## Workload and Piraeus placement

Selected infrastructure workloads, including monitoring, may run on control-plane nodes; application workloads belong on workers where workers exist. Scheduling must reserve control-plane capacity and keep general applications off those nodes. Talos settings, labels, taints, tolerations, and reservations remain TBD; single-node clusters need a policy suited to their purpose.

Pi and Metal each propose one Piraeus data plane spanning control-plane and worker nodes, with no cross-cluster replication.

| Proposed StorageClass | Diskful replica preference |
| --- | --- |
| `piraeus-infrastructure` | Control-plane nodes. |
| `piraeus-workloads` | Worker nodes. |

Names are provisional. The likely default is **Placement Count 2**: two diskful replicas per volume. Diskless quorum participants/tiebreakers may cross role boundaries and do not add data copies. Replica placement and workload scheduling are separate policies.

Pool preparation, LINSTOR properties, preference versus strict constraints, fallback, quorum, and the [encryption path](security.md#disk-encryption-and-opentofu) remain TBD. Validate maintenance and loss of a node, switch, or inter-switch link before adoption; two replicas alone do not establish availability guarantees.

[Piraeus replicated volumes](https://piraeus.io/docs/stable/tutorial/replicated-volumes/) documents Placement Count.

## UPS coordination

The coordinators and UPS assignments are listed in [inventory.md](inventory.md#shared-infrastructure), [Pi](inventory.md#pi), and [Metal](inventory.md#ups-and-shutdown-coordination). They are supporting hosts, separate from Talos nodes; management and power-return policy belong in [layout.md](layout.md#ups-shutdown-coordinators).
