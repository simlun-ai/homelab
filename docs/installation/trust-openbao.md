# Trust OpenBao workload

Trust's workload OpenTofu root installs the checksum-pinned OpenBao Helm chart
0.30.8 (OpenBao 2.7.3). One replica uses integrated Raft on a 10 GiB
`trust-zfs-retain` claim. The StatefulSet retains the claim on deletion or
scale-down. The chart requests `10.10.0.200` for the HTTPS Service and uses
cert-manager's `letsencrypt-production` ClusterIssuer for
`bao.k8s-aux.simlun.se`. OpenBao reloads the mounted TLS certificate and key
when cert-manager renews them.

The first deployment binds the API to pod loopback and leaves the pod out of
the HTTPS Service's ready endpoints. OpenTofu records the release once Helm
submits the resources. The checks below verify the first deployment.
[YubiKey-backed initialization and unseal](../security/openbao-unseal.md)
and enabling the network listener are the next rollout.

## Prepare the operator workstation

Use the existing Trust workstation, YubiKey and
[RAM-workspace flow](../../runbooks/trust-opentofu-bootstrap.md).
Confirm that `10.10.0.200` is available on VLAN 10 and that Trust's
[MetalLB pool](trust-metallb.md), `trust-zfs-retain` StorageClass and
[production ClusterIssuer](trust-cert-manager.md) are in place.

From the homelab checkout root, validate the workload configuration.

```sh
git switch feat/trust-bootstrap &&
  git pull --ff-only &&
  make -C clusters/trust tofu-workload-validate
```

On 2026-11-21, the operator validated the workload configuration on the
Trust workstation. OpenTofu 1.13.9 verified the OpenBao 0.30.8 chart checksum,
initialized the locked Helm and Kubernetes providers, and reported a valid
configuration.

The workload root uses the existing sibling
`../homelab-opentofu-state` checkout with a separate encrypted
`trust-workload.tfstate`. Use the designated single-writer checkout, updated to
the current revision, and publish any pending state changes before another apply.

```sh
git -C ../homelab-opentofu-state status --short --branch
git -C ../homelab-opentofu-state pull --ff-only
```

## Enroll the workload state key

On the first deployment, update the private records checkout and create the
workload state key. Touch the YubiKey as prompted to wrap and independently
recover the new key.

```sh
git -C secrets/wrapped switch main &&
  git -C secrets/wrapped pull --ff-only &&
  make -C clusters/trust tofu-workload-key-enroll
```

If the record already exists, verify it with the following command and reuse it.

```sh
make -C clusters/trust tofu-workload-key-verify
```

For a newly enrolled record, publish the wrapped file to the private repo
and pin the resulting submodule revision in the parent. Review each checkout
with `git status --short --branch` before committing. The private commit
should contain only the new wrapped record.

```sh
git -C secrets/wrapped add -- trust-opentofu-workload-state-r1.json &&
  git -C secrets/wrapped commit --only -m 'Enroll Trust workload state key' \
    -- trust-opentofu-workload-state-r1.json &&
  git -C secrets/wrapped push origin main &&
  git add -- secrets/wrapped &&
  git commit --only -m 'Pin the wrapped Trust workload state key' -- secrets/wrapped &&
  git push origin feat/trust-bootstrap
```

On 2026-11-21, the operator enrolled the workload state key and independently
recovered it with the YubiKey. The wrapped record was published to the private
records repository at `2e765b1` and pinned in the parent repository at
[`3512dbd`](https://github.com/simlun-ai/homelab/commit/3512dbd).

## Plan and apply

```sh
make -C clusters/trust tofu-workload-plan
```

Expect two additions on a fresh workload root, the `openbao` namespace and
the `openbao` Helm release. Review for zero changes and zero destroys.

```sh
make -C clusters/trust tofu-workload-apply
```

Review the preview again before confirming apply. Plan and apply recover the
workload state key and the Trust Talos identity.

## Verify and publish

Check the certificate, claim, server process and Service using the existing
Trust admin flow. The pod runs but stays out of the Service's ready endpoints
until the initialization rollout.

```sh
make -C clusters/trust check-tools &&
  "${HSM_VENV:-$HOME/.local/share/homelab/venvs/hsm}/bin/python" -I -B - <<'PYTHON'
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path("scripts").resolve()))
import trust_tofu as trust

trust.recovery.secrets.harden()
kubeconfig = trust.get_kubeconfig(Path("/dev/shm"))
kubectl = str(trust.SCOPE / "bin/kubectl")
with trust.recovery.config.memory_file(kubeconfig) as fd:
    base = [kubectl, "--kubeconfig", f"/proc/self/fd/{fd}", "-n", "openbao"]
    for command, timeout in (
        (["wait", "--for=condition=Ready", "certificate/openbao-api", "--timeout=600s"], 610),
        (["wait", "--for=jsonpath={.status.phase}=Bound",
          "pvc/data-openbao-0", "--timeout=120s"], 130),
        (["wait", "--for=jsonpath={.status.containerStatuses[0].state.running.startedAt}",
          "pod/openbao-0", "--timeout=120s"], 130),
        (["get", "pod/openbao-0", "pvc/data-openbao-0", "service/openbao-https", "-o", "wide"], 30),
        (["get", "endpointslice", "-l", "kubernetes.io/service-name=openbao-https", "-o", "yaml"], 30),
    ):
        subprocess.run([*base, *command], pass_fds=(fd,), check=True, timeout=timeout)
PYTHON
```

Expect a bound `trust-zfs-retain` claim, the pod on `trust-cp1`, the
Service's external IP `10.10.0.200` on TCP 443, and no ready endpoint.
Verify the external HTTPS listener after the initialization rollout, using
the [OpenBao network plan](../network.md#openbao-client-access).

Run a fresh plan and expect no changes.

```sh
make -C clusters/trust tofu-workload-plan
```

Check the workload state envelope and review the private checkout status.

```sh
python3 - ../homelab-opentofu-state/trust-workload.tfstate <<'PYTHON'
import json
import sys
from pathlib import Path

state = json.loads(Path(sys.argv[1]).read_bytes())
if not all(state.get(name) for name in ("encrypted_data", "encryption_version", "meta")):
    raise SystemExit("Missing encrypted workload state envelope")
print(f"Encrypted Trust workload state envelope, serial {state['serial']}")
PYTHON
git -C ../homelab-opentofu-state status --short --branch
```

Once the envelope check passes, commit and push only the workload state file
from the designated private checkout.

```sh
git -C ../homelab-opentofu-state add -- trust-workload.tfstate &&
  git -C ../homelab-opentofu-state commit --only -m 'Update Trust workload state' \
    -- trust-workload.tfstate &&
  git -C ../homelab-opentofu-state push origin main
```

If the runner reports a retained emergency state file, recover it before
running another workload plan or apply. Use the exact RAM path it printed.

```sh
make -C clusters/trust tofu-workload-state-recover \
  TOFU_RECOVERY_FILE=/dev/shm/trust-tofu-workload-recovery-REPLACE/errored.tfstate
```
