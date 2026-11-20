# Trust cert-manager and ACME

Trust's infrastructure OpenTofu root installs cert-manager and owns the
shared `letsencrypt-staging` and `letsencrypt-production` ClusterIssuers.
Each issuer has its own ACME account Secret. The Cloudflare solver handles
names in the public `simlun.se` zone. This configuration is ready for
operator deployment. Live issuance is pending.

The [chart pin](../../clusters/trust/tofu/cert-manager.json) records the
upstream cert-manager version and its OCI manifest digest at
`oci://quay.io/jetstack/charts/cert-manager`. The runner fetches the manifest
by digest and verifies both the manifest and chart layer before handing
the verified archive to OpenTofu.

## Prepare the wrapped token

In Cloudflare, create a dedicated API token named
`homelab-trust-cert-manager-dns` with **Zone → DNS → Edit** and
**Zone → Zone → Read**. Under **Zone Resources**, include only the specific
zone `simlun.se`. These permissions allow DNS edits throughout that zone.
Certbot on `ups-aux` retains its separate token and owns the
`_acme-challenge.kms.k8s-aux.simlun.se` challenge.

On the operator workstation, follow the
[OpenTofu bootstrap runbook](../../runbooks/trust-opentofu-bootstrap.md)
to prepare the tools and the encrypted state checkout. From the homelab
root, check out the private records branch and wrap the token at the hidden
prompt. The wrapper verifies the record before publication.

```sh
git submodule update --init -- secrets/wrapped &&
  git -C secrets/wrapped fetch origin &&
  git -C secrets/wrapped switch main &&
  git -C secrets/wrapped pull --ff-only origin main &&
  "${HSM_VENV:-$HOME/.local/share/homelab/venvs/hsm}/bin/homelab-wrap" \
    --key-id homelab/v1/trust/cert-manager/dns-api/cloudflare/r1 \
    --root-key golden-1 \
    --output secrets/wrapped/trust-cert-manager-cloudflare.json
```

Commit and push the wrapped record in the private submodule, then update the
parent pointer using the [submodule workflow](../security/encrypted-record-storage.md#checkout-and-updates).

```sh
git -C secrets/wrapped add -- trust-cert-manager-cloudflare.json &&
  git -C secrets/wrapped commit --only -m "Store wrapped Trust cert-manager DNS token" \
    -- trust-cert-manager-cloudflare.json &&
  git -C secrets/wrapped push origin main
```

## Review and apply Trust infrastructure

```sh
make -C clusters/trust tofu-plan
```

On the existing Trust installation, expect four additions if this is the
first cert-manager install. Review the namespace, cert-manager release,
Cloudflare token Secret, and Trust ACME issuer release. The existing
LocalPV resources should stay as they are.

```sh
make -C clusters/trust tofu-apply
```

Plan and apply each prompt for the wrapped state key, the Trust Talos
identity, and the cert-manager token. The runner supplies the token in the
OpenTofu process environment for that invocation. Review the apply plan and
approve it at the prompt. The same apply writes the token to the
`trust-cert-manager-cloudflare` Kubernetes Secret in `cert-manager` and
installs the issuers after cert-manager's CRDs and webhook are ready.

The token is a sensitive value in the AES-GCM-encrypted infrastructure
state. Follow the [state publication procedure](../../runbooks/trust-opentofu-bootstrap.md#3-validate-plan-and-install)
and commit only the encrypted state in the private state checkout.
Avoid decrypted state output and provider trace logging. The Kubernetes
Secret is subject to the cluster's Secret access and storage controls.
For rotation, wrap the replacement under the same key ID to a new local
ciphertext filename, then replace the current record with the verified
ciphertext. Commit the replacement and update the parent pointer, apply,
verify issuance and revoke the previous Cloudflare token. Previous encrypted
Git state revisions can still contain the previous token.

## Verify staging DNS-01

Use the operator workstation and a connected YubiKey. The following command
waits for both issuers to register, requests a temporary staging certificate,
and removes its namespace and TLS Secret on exit. A public A record and
inbound HTTP access are unnecessary for the DNS-01 test.

```sh
make -C clusters/trust check-tools &&
"${HSM_VENV:-$HOME/.local/share/homelab/venvs/hsm}/bin/python" -I -B - <<'PYTHON'
import json
import secrets as random
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path("scripts").resolve()))
import trust_tofu as trust

trust.recovery.secrets.harden()
ram_root = Path("/dev/shm")
kubeconfig = trust.get_kubeconfig(ram_root)
kubectl = str(trust.SCOPE / "bin/kubectl")
namespace = "trust-acme-check-" + random.token_hex(4)

with trust.recovery.config.memory_file(kubeconfig) as fd:
    def kub(*args, **kwargs):
        return subprocess.run(
            [kubectl, "--kubeconfig", f"/proc/self/fd/{fd}",
             "--request-timeout=330s", *args],
            pass_fds=(fd,), check=True, **kwargs,
        )

    kub("wait", "--for=condition=Ready", "--timeout=120s",
        "clusterissuer/letsencrypt-staging", "clusterissuer/letsencrypt-production")
    kub("create", "namespace", namespace)
    try:
        certificate = {
            "apiVersion": "cert-manager.io/v1",
            "kind": "Certificate",
            "metadata": {"name": "dns01-check"},
            "spec": {
                "secretName": "dns01-check-tls",
                "dnsNames": ["trust-acme-check.k8s-aux.simlun.se"],
                "issuerRef": {"kind": "ClusterIssuer", "name": "letsencrypt-staging"},
            },
        }
        kub("-n", namespace, "create", "-f", "-", input=json.dumps(certificate), text=True)
        kub("-n", namespace, "wait", "--for=condition=Ready", "--timeout=300s",
            "certificate/dns01-check")
        print("PASS: Let's Encrypt staging issued the DNS-01 certificate.", flush=True)
    except subprocess.CalledProcessError:
        try:
            kub("-n", namespace, "get", "certificate,certificaterequest,order,challenge")
        except subprocess.CalledProcessError:
            pass
        raise
    finally:
        kub("delete", "namespace", namespace, "--timeout=90s")
PYTHON
```

A Ready ClusterIssuer confirms ACME account registration. The Ready staging
Certificate confirms the DNS-01 workflow. Production issuance is first tested
when the OpenBao workload requests its real certificate.

## Planned cross-cluster certificate delivery

Trust will also run External Secrets Operator as part of the
[certificate factory](../clusters.md#certificate-factory). It will publish
selected cert-manager TLS Secrets to OpenBao using one `PushSecret` per
certificate. Backup's Garage HTTPS endpoint will be the first consumer,
using an `ExternalSecret` in Backup to fetch and refresh its local TLS Secret.
This runbook installs cert-manager and its shared issuers. The publication
and consumption steps will be documented with the later rollout.

## OpenBao network prerequisites

OpenBao's future workload root will own its `Certificate` for
`bao.k8s-aux.simlun.se` and use `letsencrypt-production`. Once the private
HTTPS endpoint IP is assigned, add the UniFi A record and cross-VLAN rules
described in the [network overview](../network.md#openbao-client-access).
Verify DNS resolution and HTTPS from each dependent VLAN before configuring
clients. The OpenBao address and workload are pending.
