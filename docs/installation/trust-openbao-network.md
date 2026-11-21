# Enable the Trust OpenBao network listener

This upgrades the [initialized Trust OpenBao instance](trust-openbao-initialize.md)
on its existing Raft claim. OpenBao listens on pod IPv4 port 8200 and the
MetalLB Service exposes HTTPS on `10.10.0.200:443`. Raft's cluster listener
stays on loopback for the single replica. The chart adds a configuration
checksum to the pod template. The StatefulSet uses `OnDelete`, so the
operator explicitly replaces the old pod after applying. The replacement
starts sealed and joins the Service's ready endpoints after manual unseal.

In UniFi, set the local A record `bao.k8s-aux.simlun.se` to `10.10.0.200`.
For Pi and Metal clients and their UPS coordinators, allow only TCP 443 to
that address ahead of the inter-VLAN deny rules. Backup and `ups-aux` share
VLAN 10. See the [OpenBao client access plan](../network.md#openbao-client-access).

## Plan and apply

From the `homelab` checkout root on the Trust operator workstation with the
YubiKey connected, update the checkout and confirm the server is initialized.

```sh
git switch feat/trust-bootstrap &&
  git pull --ff-only --no-recurse-submodules &&
  make -C clusters/trust openbao-status
```

Expect `Initialized: True. Sealed: False.` before proceeding. If the existing
server is sealed, use `make -C clusters/trust openbao-unseal` and confirm its
status again.

```sh
make -C clusters/trust tofu-workload-plan
```

Expect `0 to add, 1 to change, 0 to destroy`. The change is an in-place
update of `helm_release.openbao`.

```sh
make -C clusters/trust tofu-workload-apply
```

Confirm the same plan in the apply preview. Helm returns when the release
is submitted so the operator can unseal the replacement before readiness.

## Wait for the replacement and unseal

Run the following from the checkout root. It waits for the StatefulSet to
observe the new template, gracefully deletes the old pod once if needed, and
waits for the replacement container to run. The retained claim carries the
initialized Raft data across the restart.

```sh
make -C clusters/trust check-tools &&
  "${HSM_VENV:-$HOME/.local/share/homelab/venvs/hsm}/bin/python" -I -B - <<'PYTHON'
import json
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path("scripts").resolve()))
import trust_tofu as trust

trust.recovery.secrets.harden()
kubeconfig = trust.get_kubeconfig(Path("/dev/shm"))
kubectl = str(trust.SCOPE / "bin/kubectl")
with trust.recovery.config.memory_file(kubeconfig) as fd:
    base = [kubectl, "--kubeconfig", f"/proc/self/fd/{fd}", "-n", "openbao"]

    def get(resource):
        result = subprocess.run(
            [*base, "get", resource, "--ignore-not-found", "-o", "json"],
            pass_fds=(fd,), check=True, stdout=subprocess.PIPE, timeout=15,
        )
        return json.loads(result.stdout) if result.stdout else {}

    deadline = time.monotonic() + 180
    restart_requested = False
    while time.monotonic() < deadline:
        sts = get("statefulset/openbao")
        pod = get("pod/openbao-0")
        sts_status = sts.get("status", {})
        revision = sts_status.get("updateRevision")
        pod_metadata = pod.get("metadata", {})
        annotations = pod_metadata.get("annotations", {})
        statuses = pod.get("status", {}).get("containerStatuses", [])
        template_annotations = (
            sts.get("spec", {}).get("template", {}).get("metadata", {}).get("annotations", {})
        )
        checksum = template_annotations.get("openbao.hashicorp.com/config-checksum")
        observed = sts_status.get("observedGeneration") == sts.get("metadata", {}).get("generation")
        if revision and checksum and observed and pod_metadata and not pod_metadata.get("deletionTimestamp"):
            pod_revision = pod_metadata.get("labels", {}).get("controller-revision-hash")
            if pod_revision != revision and not restart_requested:
                subprocess.run(
                    [*base, "delete", "pod/openbao-0", "--wait=false"],
                    pass_fds=(fd,), check=True, timeout=30,
                )
                restart_requested = True
            if (
                pod_revision == revision
                and annotations.get("openbao.hashicorp.com/config-checksum") == checksum
                and any(s["name"] == "openbao" and "running" in s["state"] for s in statuses)
            ):
                print(f"OpenBao replacement is running at revision {revision}.")
                break
        time.sleep(3)
    else:
        raise SystemExit("Timed out waiting for the OpenBao replacement.")
PYTHON
```

```sh
make -C clusters/trust openbao-unseal
```

Expect `PASS: OpenBao is initialized and unsealed.`

## Verify HTTPS and publish state

Test from a client on VLAN 10 first. The explicit address bypasses local DNS
while still verifying the production TLS hostname and certificate chain.

```sh
curl --fail --silent --show-error --noproxy '*' --max-time 10 --write-out '\nHTTP %{http_code}\n' \
  --resolve bao.k8s-aux.simlun.se:443:10.10.0.200 \
  https://bao.k8s-aux.simlun.se/v1/sys/health
```

Expect HTTP 200 with `"initialized":true` and `"sealed":false`.
Then verify local DNS and HTTPS from VLAN 10 and from the permitted Pi and
Metal client networks.

```sh
getent ahostsv4 bao.k8s-aux.simlun.se &&
  curl --fail --silent --show-error --noproxy '*' --max-time 10 --write-out '\nHTTP %{http_code}\n' \
    https://bao.k8s-aux.simlun.se/v1/sys/health
```

Expect DNS to resolve to `10.10.0.200` and the same health result. Run
`make -C clusters/trust tofu-workload-plan` and expect no changes, then
[check and publish the encrypted workload state](trust-openbao.md#publish-encrypted-workload-state).
