# Clusters

## Vault

The Vault cluster is the foundational cluster: it does not depend on any of the other clusters, while all other clusters depend on services it provides. To avoid circular dependencies, the Vault cluster's own secrets are entered manually rather than retrieved from OpenBao.

### Platform and networking

- Single-node Talos Kubernetes cluster.
- Flannel for pod networking (no Cilium).
- MetalLB for LoadBalancer services.
- Traefik for ingress.
- Headlamp for Kubernetes management.

### Storage and backups

- Two USB SSDs in a mirrored ZFS pool.
- zfs-localpv for local persistent volumes.
- Backups to Cloudflare R2, including the OpenBao PVC.

### Monitoring and alerting

- kube-prometheus-stack (Prometheus, Grafana, and Alertmanager).
- Alertmanager notifications via Telegram.

### Secrets and certificates

- OpenBao provides centralized secrets management for dependent clusters; the Vault cluster does not rely on it for its own secrets.
- cert-manager issues Let's Encrypt certificates using Cloudflare DNS-01 validation.
- External Secrets Operator uses PushSecret to publish cert-manager certificates to OpenBao.
- Dependent clusters use External Secrets Operator connected to OpenBao to pull certificates.

## Backup

## Pi

## Metal
