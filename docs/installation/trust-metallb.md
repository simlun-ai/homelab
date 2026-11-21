# Trust MetalLB and OpenBao's service address

Trust's infrastructure OpenTofu root installs MetalLB in Layer 2 mode
on VLAN 10. The chart uses the native speaker with the FRR backends disabled.
The speaker is allowed to advertise from the single control-plane node,
`trust-cp1`, even if the node carries the control-plane load-balancer
exclusion label. The speaker uses host networking in the `metallb-system`
namespace.

A separate Helm release installs the address pool and Layer 2 advertisement
after MetalLB's CRDs and controller are ready. The `trust-services` pool
covers Trust's reserved range of `10.10.0.200`–`10.10.0.209` and disables
automatic allocation. OpenBao will explicitly request `10.10.0.200`.
See the [VLAN 10 pool assignments](../network.md#kubernetes-networking).

## Install from the operator workstation

Review the plan with the YubiKey connected.

```sh
git pull --ff-only &&
  make -C clusters/trust tofu-plan
```

On the existing Trust installation, expect three additions. They are the
`metallb-system` namespace, the `metallb` Helm release, and the
`trust-metallb-config` Helm release.

```sh
make -C clusters/trust tofu-apply
```

After apply, wait for the controller and speaker and confirm the Trust
pool and Layer 2 advertisement. This uses the existing Trust admin flow.

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
    base = [kubectl, "--kubeconfig", f"/proc/self/fd/{fd}", "-n", "metallb-system"]
    for resource in ("deployment/metallb-controller", "daemonset/metallb-speaker"):
        subprocess.run(
            [*base, "rollout", "status", resource, "--timeout=120s"],
            pass_fds=(fd,), check=True, timeout=130,
        )
    subprocess.run(
        [*base, "get", "pods", "-o", "wide"],
        pass_fds=(fd,), check=True, timeout=30,
    )
    subprocess.run(
        [*base, "get", "ipaddresspool/trust-services",
         "l2advertisement/trust-services", "-o", "yaml"],
        pass_fds=(fd,), check=True, timeout=30,
    )
PYTHON
```

Expect the speaker to be ready on `trust-cp1`, the pool to contain
`10.10.0.200-10.10.0.209` with `autoAssign: false`, and the advertisement to
reference that pool. Run a fresh plan and publish the encrypted state
following the [OpenTofu runbook](../../runbooks/trust-opentofu-bootstrap.md#3-validate-plan-and-install).

## Rollout record

On 2026-11-21, the operator confirmed `3 to add, 0 to change, 0 to destroy`
in the plan and `3 added, 0 changed, 0 destroyed` after apply for
[PR #47](https://github.com/simlun-ai/homelab/pull/47). The encrypted
infrastructure state was
[published](https://github.com/simlun-ai/homelab-opentofu-state/commit/1ca23c33c1578d0919fe47eabda72037f062602e).
The workload rollout will verify OpenBao's address assignment and HTTPS.

## Use the address when deploying OpenBao

Confirm `10.10.0.200` is free on VLAN 10 before deploying the OpenBao Service.
The [OpenBao workload](trust-openbao.md) defines a `LoadBalancer` Service
for TCP 443 and requests the IP with
`metallb.io/loadBalancerIPs: "10.10.0.200"`. MetalLB advertises the address
when the Service has a ready endpoint. Verify assignment during workload
deployment and reachability after initialization enables the network listener.

In UniFi, create the local A record `bao.k8s-aux.simlun.se` → `10.10.0.200`
and allow TCP 443 to that address from the Pi and Metal cluster clients
and their coordinators. **Backup and `ups-aux` share VLAN 10**. Verify access
from them on the local network as well.

After the OpenBao Service is ready, confirm Kubernetes assigned
`10.10.0.200`. Check name resolution and HTTPS from each client network with
the production certificate, following the
[OpenBao network plan](../network.md#openbao-client-access).
