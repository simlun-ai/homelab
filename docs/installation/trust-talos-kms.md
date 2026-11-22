# Deploy the Trust-hosted Talos KMS for Backup

This is the first deployment of the [shared adapter](../security/security.md#talos-kms-adapter).
Use the same image and chart for Pi and Metal when those clusters are ready.
Trust's own bootstrap KMS continues to run on `ups-aux`.

## Prepare the image and Backup registration

From the homelab checkout root on the operator workstation, follow
[Publish the first image](trust-zot.md#publish-the-first-image) to build
and push the ARM64 adapter to Trust's Zot registry and record its digest.

In `clusters/trust/tofu-workload/talos-kms.json`, set `image` to
`registry.k8s-aux.simlun.se/homelab/talos-kms@sha256:...` using that digest. In
`clusters.backup.nodes`, add the first Backup node's actual Talos hardware
UUID as the key and its static early-boot IP as the value. Commit those
non-secret settings as part of the deployment. An empty node map leaves
that cluster undeployed.

Create a UniFi internal DNS record for `kms-backup.k8s-aux.simlun.se`
pointing to `10.10.0.201`. The chart requests that IP from Trust MetalLB
and issues a public TLS certificate with the existing production
cert-manager issuer. The Service preserves the client IP. The adapter
checks the configured source-IP and UUID pair before each RPC. The
allowlist limits which traffic the service accepts within the trusted
network.

## Configure OpenBao and deploy

With Trust OpenBao unsealed, bootstrap the Backup Transit key and the
Kubernetes auth role from the operator workstation. The helper prompts
for the YubiKey and streams the existing wrapped root credential's
plaintext through stdin. It keeps the existing key when rerun.

```sh
make -C clusters/trust openbao-kms-auth KMS_CLUSTER=backup
make -C clusters/trust tofu-workload-plan
```

For the first registration, expect one new Helm release,
`helm_release.talos_kms["backup"]`, and no other changes. Apply and wait for
the certificate and the adapter.

```sh
make -C clusters/trust tofu-workload-apply
make -C clusters/trust trust-kubectl \
  KUBECTL_ARGS='-n talos-kms wait --for=condition=Ready certificate/talos-backup --timeout=5m'
make -C clusters/trust trust-kubectl \
  KUBECTL_ARGS='-n talos-kms rollout status deployment/talos-backup --timeout=5m'
make -C clusters/trust trust-kubectl \
  KUBECTL_ARGS='-n talos-kms get service/talos-backup'
```

Expect the Service at `10.10.0.201`. The rollout confirms the TLS listener
is ready. The first Backup boot verifies OpenBao login and actual unlock.
Each RPC exchanges the current projected pod identity for a short-lived
OpenBao batch token, then calls the cluster's scoped Transit endpoint.

## Verify the first encrypted Backup boot

Use `https://kms-backup.k8s-aux.simlun.se:443` for both Talos KMS volume
keys. Configure the registered static address and early-boot DNS and time
as part of the Backup install. After the first encrypted start, verify
`STATE` and `EPHEMERAL` unlock through the adapter and record the result in
the [Trust roadmap](02-trust.md#next-milestone-first-backup-kms-boot).
If boot fails, inspect the Backup console and the `talos-backup` pod logs,
then use the Trust early-boot rehearsal in the roadmap to isolate the issue.

After verifying a clean workload plan, follow the [encrypted workload state
publication procedure](trust-openbao.md#publish-encrypted-workload-state).
