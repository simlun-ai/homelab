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
| [Talos KMS adapter](security/security.md#talos-kms-adapter) (repository-owned Python service) | TBD | TBD |  |  |  |
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
| Make, Bash | TBD. |
| Python (parent helpers) | 3.13–3.14 on Linux; the HSM code submodule maintains its own support range. |
| Ruff | Development-only Python lint/format checks; pinned in [pyproject.toml](../pyproject.toml) and the CI tool stage. |
| Docker with Buildx/BuildKit | Root `make ci` validation; [CI prerequisites](../ci/README.md). |
| Python cryptography (HKDF/AESGCM), constrained RFC 8785 serialization | Initial [v1 wrapping helper](security/security.md#challenges-derivation-and-wrapped-credentials); step 00 pins live in [the code project’s pyproject.toml](../tools/homelab-hsm/homelab_secrets/pyproject.toml). |
| YubiKey Manager Python SDK | Selected for [step 00](installation/00-yubikey-setup.md); version pinned in [the code project’s pyproject.toml](../tools/homelab-hsm/homelab_secrets/pyproject.toml), physical-device verification pending. |
| kubectl, talosctl, Helm, OpenBao CLI (`bao`) | TBD per scope; talosctl must be compatible with Talos. |
| OpenTofu CLI (`tofu`) | Independently pinned per scope; catalog version above. |
| Raspberry Pi OS Lite | 64-bit; exact image release TBD. Selected for all UPS coordinators on microSD; [base setup](../runbooks/ups-coordinator-base-setup.md). |
| Ansible | ansible-core and dependencies pinned in [requirements.txt](../support/ups/requirements.txt); base bootstrap implemented, hardware verification pending. |
| nftables, unattended-upgrades | Raspberry Pi OS repository versions; [shared hardening](security/coordinator-hardening.md) implemented, hardware verification pending. |
| [Vault bootstrap KMS](security/security.md#vault-bootstrap-kms) (repository-owned Python gRPC service), ACME client | TBD; planned on the Vault/Backup coordinator, independently of cluster services. |
