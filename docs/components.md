# Components

Cluster entries are **planned** placements at the catalog version, not deployed versions or [operational pins](layout.md#tool-versions-and-command-scopes). Blank means placement is unspecified. Immich and Frigate's Metal assignments are tentative, inferred from [dedicated storage pools](inventory.md#workers).

## Infrastructure

| Component | Latest version | Vault | Backup | Pi | Metal |
| --- | --- | --- | --- | --- | --- |
| Talos | v1.14.2 | v1.14.2 | v1.14.2 | v1.14.2 | v1.14.2 |
| Piraeus Operator | v2.12.0 |  |  | v2.12.0 | v2.12.0 |
| ZFS (Talos system extension) | v2.4.4 | v2.4.4 | v2.4.4 | v2.4.4 | v2.4.4 |
| Cilium | v1.20.2 |  |  |  |  |
| Flannel | v0.28.9 | v0.28.9 |  |  |  |
| MetalLB | v0.16.0 | v0.16.0 |  |  |  |
| Traefik | v3.7.14 | v3.7.14 |  |  |  |
| kube-prometheus-stack (Helm chart) | v92.3.0 | v92.3.0 |  |  |  |
| Loki | v3.7.8 |  |  |  |  |
| ZFS LocalPV | v2.11.1 | v2.11.1 |  |  |  |
| OpenBao | v2.7.1 | v2.7.1 |  |  |  |
| OpenTofu | v1.13.1 |  |  |  |  |
| External Secrets Operator | v2.11.0 | v2.11.0 | v2.11.0 | v2.11.0 | v2.11.0 |
| cert-manager | v1.21.2 | v1.21.2 |  |  |  |
| Garage | v2.4.1 |  |  |  |  |
| PostgreSQL | v18.6 |  |  |  |  |
| Headlamp | v0.45.0 | v0.45.0 |  |  |  |

## Workloads

| Component | Latest version | Vault | Backup | Pi | Metal |
| --- | --- | --- | --- | --- | --- |
| Zigbee2MQTT | v2.14.2 |  |  |  |  |
| Home Assistant | 2026.10.0 |  |  |  |  |
| Immich | v3.3.1 |  |  |  | v3.3.1 |
| Syncthing | v2.1.6 |  |  |  |  |
| Jellyfin | v12.2 |  |  |  |  |
| Frigate NVR | v0.18.0 |  |  |  | v0.18.0 |

## Management tooling and supporting hosts (planned)

| Tool / OS | Version |
| --- | --- |
| Make, Python, Bash | TBD. |
| kubectl, talosctl, Helm, OpenBao CLI (`bao`) | TBD per scope; talosctl must be compatible with Talos. |
| OpenTofu CLI (`tofu`) | Independently pinned per scope; catalog version above. |
| Raspberry Pi OS Lite, Ansible | TBD; [candidate UPS-host stack](layout.md#ups-shutdown-coordinators). |
