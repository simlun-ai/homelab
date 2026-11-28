# Deploy Headlamp on Trust

Headlamp serves the Trust cluster at `https://headlamp.k8s-aux.simlun.se/`.
It terminates TLS using a certificate from Trust's production DNS-01 issuer.
The deployment uses the existing Trust MetalLB pool and requests
`10.10.0.203` on TCP 443. Add a local UniFi A record pointing to that address
and allow TCP 443 from the operator network.

## Deploy and verify

Run `make -C clusters/trust tofu-workload-plan`. Expect two additions for the
namespace and Helm release. Review the plan and run
`make -C clusters/trust tofu-workload-apply`.

Check that `certificate/headlamp` is Ready and `deployment/headlamp` is
available in the `headlamp` namespace. Verify that `service/headlamp-https`
has the planned IP and open the LAN URL.

From the operator workstation, issue a viewer token and paste it into the
Headlamp sign-in form.

```sh
make -s --no-print-directory -C clusters/trust headlamp-login-token | pbcopy
```

Touch the YubiKey when prompted. The command requests a one-hour Kubernetes
token for `headlamp-viewer`, which uses the built-in `view` role and has
read-only access to node objects. Check that
the UI can list nodes and workloads and that the viewer cannot read Secrets
or change workloads. The Headlamp pod uses a separate service account.

Verify a clean workload plan and
[publish the encrypted workload state](trust-openbao.md#publish-encrypted-workload-state).

## Certificate renewal

Headlamp v0.45.0 loads its TLS key pair at startup. After cert-manager renews
the Secret, restart `deployment/headlamp` in the `headlamp` namespace and
verify that the LAN endpoint serves the renewed certificate. Record the first
renewal check after deployment.
