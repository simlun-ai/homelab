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

On 2026-11-21, the operator confirmed the listener upgrade plan showed
`0 to add, 1 to change, 0 to destroy`. The apply completed with
`0 added, 1 changed, 0 destroyed`. The replacement pod started at
revision `openbao-6999b88b66`, and the YubiKey unseal helper confirmed that
OpenBao was initialized and unsealed. From the operator workstation,
HTTPS through MetalLB at `10.10.0.200:443` returned HTTP 200 with
`initialized: true`, `sealed: false`, and `standby: false`. The probe verified
the production TLS hostname using an explicit IP override. After the local
A record was configured, UniFi resolver `10.10.0.1` and the workstation's
normal resolver both returned `10.10.0.200`. HTTPS without an IP override
returned HTTP 200 with OpenBao initialized, unsealed, and active. The
operator deferred Pi and Metal DNS and HTTPS checks until those client VLANs
are set up. The follow-up OpenTofu plan reported no changes. The operator
verified the encrypted workload state envelope at serial 2 and
[published the state](https://github.com/simlun-ai/homelab-opentofu-state/commit/b57bfc6c2d1f514be3c80de05bb399ec70d0694b).

## Wait for the replacement and unseal

`openbao-restart` waits for the StatefulSet to observe its template, gracefully
replaces the production pod, and waits for the new container to run. The
retained claim carries the Raft data across the restart. The single-replica
API is unavailable until the replacement has been unsealed.

```sh
make -C clusters/trust openbao-restart
```

Expect `OpenBao replacement is running at revision …`. If the command times
out after requesting replacement, inspect the pod before retrying.

```sh
make -C clusters/trust openbao-unseal
```

Expect `PASS: OpenBao is initialized and unsealed.`

## Verify HTTPS and publish state

The OpenBao UI is served at [the existing HTTPS address](https://bao.k8s-aux.simlun.se/ui/).
After replacing and unsealing the pod, verify that this URL loads the sign-in page.

Test from a client on VLAN 10 first. The explicit address bypasses local DNS
while still verifying the production TLS hostname and certificate chain.

```sh
curl --fail --silent --show-error --noproxy '*' --max-time 10 --write-out '\nHTTP %{http_code}\n' \
  --resolve bao.k8s-aux.simlun.se:443:10.10.0.200 \
  https://bao.k8s-aux.simlun.se/v1/sys/health
```

Expect HTTP 200 with `"initialized":true` and `"sealed":false`.
Then verify local DNS and HTTPS from VLAN 10. Repeat the same check from
permitted Pi and Metal clients when their VLANs are available.

```sh
getent ahostsv4 bao.k8s-aux.simlun.se &&
  curl --fail --silent --show-error --noproxy '*' --max-time 10 --write-out '\nHTTP %{http_code}\n' \
    https://bao.k8s-aux.simlun.se/v1/sys/health
```

Expect DNS to resolve to `10.10.0.200` and the same health result. Run
`make -C clusters/trust tofu-workload-plan` and expect no changes, then
[check and publish the encrypted workload state](trust-openbao.md#publish-encrypted-workload-state).

## Sign in to the web UI

On the Trust operator workstation, use the YubiKey to issue a non-renewable
token with OpenBao's `default` policy and a one-hour lifetime.

```sh
make -s --no-print-directory -C clusters/trust openbao-ui-token | pbcopy
```

At [the OpenBao UI](https://bao.k8s-aux.simlun.se/ui/), choose **Token** and
paste the clipboard into the sign-in form. The command keeps the recovered
root token in memory and streams the temporary token to the clipboard.
