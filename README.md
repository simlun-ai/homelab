# Homelab

This repository defines and documents my planned homelab infrastructure: four Talos Linux Kubernetes clusters with distinct responsibilities. **Vault** and **Backup** provide supporting infrastructure, while **Pi** and **Metal** host the primary workloads.

## Goals

- **Expect disk failures, not major interruptions.** Design storage and workload placement to tolerate ordinary disk failures without major service disruption.
- **Passwordless clusters.** YubiKeys serve as tiny HSMs holding a golden secret. Other keys and secrets ultimately derive from it, either directly through the YubiKeys or through OpenBao.
- **Separate supporting services from applications.** Vault and Backup are auxiliary; Pi provides efficient, always-on home automation, while Metal handles heavier workloads.

## Clusters

| Cluster | Purpose | Expected workloads |
| --- | --- | --- |
| **Vault** | Independent root of trust for the other clusters. | OpenBao and its minimal supporting services. |
| **Backup** | Backup and recovery infrastructure. | Backup storage and recovery services (implementation TBD). |
| **Pi** | Small, low-power primary workload cluster. | Home Assistant, Zigbee2MQTT, and other home automation services. |
| **Metal** | Larger, high-performance primary workload cluster. | Frigate, Immich, Crypto, media services, databases, and other compute- or storage-intensive applications. |

Start with the [installation plan and TODO list](docs/installation/README.md). See [docs/clusters.md](docs/clusters.md) for cluster architecture and [docs/](docs/) for further details.
