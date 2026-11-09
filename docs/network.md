# Network overview

The UniFi Cloud Gateway Ultra provides the three VLANs, DHCP, inter-VLAN routing, and firewall enforcement. Netgear managed switches carry the VLANs using 802.1Q tagging. Each VLAN uses `10.<VLAN_ID>.0.0/24` with a gateway at `.1`.

## VLANs and DHCP

| VLAN | UniFi network | DNS domain | Subnet | Gateway | DHCP start | DHCP end | Purpose |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 10 | `k8s-aux` | `k8s-aux.lundmark.internal` | `10.10.0.0/24` | `10.10.0.1` | `10.10.0.241` | `10.10.0.254` | Trust (OpenBao), Backup (Garage), and their shared UPS coordinator |
| 11 | `k8s-pi` | `k8s-pi.lundmark.internal` | `10.11.0.0/24` | `10.11.0.1` | `10.11.0.241` | `10.11.0.254` | Pi cluster |
| 12 | `k8s-metal` | `k8s-metal.lundmark.internal` | `10.12.0.0/24` | `10.12.0.1` | `10.12.0.241` | `10.12.0.254` | Metal cluster |

In UniFi, use subnet mask `255.255.255.0` on all three networks. Each DHCP pool has 14 addresses.

## Address allocation

The last octet has the same meaning on all three VLANs.

| Last octet | Allocation |
| --- | --- |
| `.0` | Network address |
| `.1` | UniFi gateway |
| `.2`–`.9` | Infrastructure |
| `.10`–`.19` | Talos control plane |
| `.20`–`.29` | Talos workers |
| `.30`–`.191` | Reserved |
| `.192` | Load balancer block start, unused |
| `.193`–`.222` | Load balancers |
| `.223` | Load balancer block end, unused |
| `.224`–`.239` | Reserved |
| `.240` | DHCP block start, unused |
| `.241`–`.254` | DHCP clients |
| `.255` | Broadcast |

`10.<VLAN_ID>.0.192/27` and `10.<VLAN_ID>.0.240/28` are logical reservations for load balancers and DHCP. Each VLAN is routed as a single `/24`, and hosts use that prefix length. Match load balancer traffic with one `/27` per VLAN in UniFi firewall rules. Scope access to sensitive endpoints such as OpenBao more narrowly.

### Confirmed static addresses

| Host | Address |
| --- | --- |
| `ups-aux.k8s-aux.lundmark.internal` (`ups-aux`, Raspberry Pi 3) | `10.10.0.5` |
| `trust-cp1.k8s-aux.lundmark.internal` (Trust Talos node) | `10.10.0.10` |
| Backup Talos node | `10.10.0.15` |

Individual Pi and Metal node addresses and the addresses for `ups-pi` and `ups-metal` are TBD.

## Required DNS entries

| Type | DNS name | Value | Purpose | Status |
| --- | --- | --- | --- | --- |
| A | `trust-api.k8s-aux.lundmark.internal` | `10.10.0.10` | Trust Kubernetes API | Configured; resolution verified 2026-11-08 |
| A | `ups-aux.k8s-aux.lundmark.internal` | `10.10.0.5` | Coordinator SSH and Ansible | UniFi device **Local DNS Record** enabled. Ansible connected using the name on 2026-11-09. |
| A | `kms.k8s-aux.simlun.se` | `10.10.0.5` | Trust coordinator KMS TLS endpoint | UniFi resolver `10.10.0.1` returned `10.10.0.5` from `simlun-x1`; the Pi also resolved the name during its static network rehearsal (2026-11-09) |

### Configure on the UniFi gateway

For the `ups-aux` SSH hostname, open the `ups-aux` device in UniFi Network,
enable **Local DNS Record**, and set it to `ups-aux.k8s-aux.lundmark.internal`.
The operator verified this method on 2026-11-09.

For a DNS policy, use **Settings → Policy Table → Create New Policy → DNS**.
This path was verified on the Cloud Gateway Ultra on 2026-11-08. Select
**Host (A)**, enter the DNS name and address from the table, then click **Add**.
Enter the hostname alone, without `https://` or a port.

### Verify resolution

The operator verified both the gateway directly and the normal workstation
resolver from `simlun-x1` on 2026-11-08:

```sh
dig @10.10.0.1 trust-api.k8s-aux.lundmark.internal +short
getent ahostsv4 trust-api.k8s-aux.lundmark.internal
```

Both resolved to `10.10.0.10`. Clients must use the gateway's DNS service,
directly or through a resolver forwarding this domain to it.

## Kubernetes API endpoint

Trust's client URL is `https://trust-api.k8s-aux.lundmark.internal:6443`.
The required DNS entry above points directly to the single control-plane node;
no API load balancer is introduced. Talos administration continues to target
the explicit node address independently of this Kubernetes DNS name.
DNS verification does not establish that the Kubernetes API is running.

## Kubernetes networking

All four clusters are independent, including Trust and Backup on VLAN 10. The CNI and load balancer choices are planned. The proposed pod and service CIDRs are disjoint from each other and from all three VLANs.

| [Cluster](clusters.md) | VLAN | Talos topology | CNI | Load balancer | Proposed pod CIDR | Proposed service CIDR |
| --- | --- | --- | --- | --- | --- | --- |
| Trust | 10 | Single node | Flannel | MetalLB L2 | `10.128.0.0/16` | `10.240.0.0/16` |
| Backup | 10 | Single node | Flannel | MetalLB L2 | `10.129.0.0/16` | `10.241.0.0/16` |
| Pi | 11 | Multiple nodes | Cilium | Cilium | `10.130.0.0/16` | `10.242.0.0/16` |
| Metal | 12 | Multiple nodes | Cilium | Cilium | `10.131.0.0/16` | `10.243.0.0/16` |

On the shared VLAN, reserve `10.10.0.200`–`10.10.0.209` for Trust's MetalLB pool and `10.10.0.210`–`10.10.0.219` for Backup's. Individual service addresses remain TBD. The separate [Metal storage network](clusters.md#dedicated-storage-network) has its own addressing TBD.

## Gateway and UPS outages

Trust and Backup share a UPS. The plan is for `ups-aux` to run `talosctl` against their static node addresses. This path can work during a gateway outage while the switch path remains powered and VLAN 10 stays intact. Inter-VLAN traffic requires the gateway. The [Trust cold-start procedure](security/security.md#trust-bootstrap-kms) still depends on working DNS and public NTP.

Temporary OpenBao and Garage outages are acceptable. Running clusters can continue using Kubernetes Secrets already synchronized by External Secrets Operator while OpenBao is unavailable. New and refreshed values require OpenBao to be reachable. Garage is intended for periodic backups, with schedules and retention covered by the [backup design](backup-and-restore.md).

## Trust KMS endpoint readiness

The coordinator KMS endpoint is separate from the Kubernetes API and direct
Talos administration address. The selected endpoint is
`https://kms.k8s-aux.simlun.se:443`, serving gRPC over TLS on TCP 443.
Its internal A record resolved to `10.10.0.5` from both the workstation and
the Pi during the [network rehearsal](installation/02-trust.md#experiment-record-and-acceptance-checks).
The Pi's connection to TCP 443 timed out. A public certificate will use [Cloudflare DNS-01](installation/trust-kms-cloudflare.md);
DNS-01 issuance does not require exposing the KMS listener to the Internet. Independent public NTP endpoints and pre-STATE network/DNS/time
configuration also remain pending. See the [draft KMS contract](security/trust-bootstrap-kms.md#proposed-readiness-tls-and-admission-behavior).
Same-VLAN Trust/coordinator traffic requires host/switch admission consideration;
inter-VLAN gateway rules alone do not isolate VLAN 10 peers.
