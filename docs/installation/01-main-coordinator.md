# 01 - Main coordinator

**Locked production TLS verified on `ups-aux`; live-node authorization pending.**

First complete the shared [UPS coordinator base setup](../../runbooks/ups-coordinator-base-setup.md) for `ups-aux` at `10.10.0.5`, the Trust/Backup host. That runbook owns Raspberry Pi OS Lite installation, SSH access, and Ansible bootstrap for all three coordinators.

This step adds only Trust's independent Talos bootstrap KMS and its supporting TLS/ACME services. Complete [YubiKey setup](00-yubikey-setup.md) before authorizing KMS credentials.

## Additional KMS setup — TODO

The [draft Trust KMS contract](../security/trust-bootstrap-kms.md) records the
pinned Talos interface, proposed envelope/session protocol, open choices and
acceptance criteria. It is documentation, not a deployed or verified service.

- [x] Implement disposable software-only envelope/session tests for the approved behavior, with a fixed public vector. This verifies the envelope and session core.
- [x] Verify the [loopback gRPC-over-TLS rehearsal](../../support/hsm/README.md#trust-kms-loopback-rehearsal) on the operator workstation (Python 3.13.18, 2026-11-09).
- [x] Verify the [local authorization and worker rehearsal](../../support/hsm/README.md#trust-kms-loopback-rehearsal) on the operator workstation (three tests passed, 2026-11-09).
- [ ] Settle UUID mapping, early-boot NTP/networking, admission rules and independent recovery inputs. The public TLS endpoint is selected as `https://kms.k8s-aux.simlun.se:443`. The [UniFi DNS record](../network.md#required-dns-entries) resolved to `10.10.0.5` from the workstation and the Pi. The initial Pi TCP probe timed out. After listener deployment, the repeat probe from `10.10.0.10` and DHCP rollback passed on 2026-11-11. Native Talos TLS and KMS verification remain pending.
- [ ] Configure independent DNS/time readiness for the coordinator and Trust under the [bootstrap KMS design](../security/security.md#trust-bootstrap-kms).
- [x] Stage the locked service on `ups-aux` and verify it reports an empty authorization window (2026-11-09).
- [x] Verify the [Certbot staging rehearsal](trust-kms-cloudflare.md#run-the-staging-rehearsal) on `ups-aux`: issuance, renewal with the same TLS key, RAM workspace cleanup and the post-run public DNS check passed (2026-11-10).
- [x] Validate the [wrapped staging state lifecycle](trust-kms-cloudflare.md#wrapped-staging-state-initialize-recover-and-recreate): coordinator-local import/initialization, default recovery, explicit recreation and archival. Coordinator-local import, default recovery/renewal, explicit recreation and recovery/renewal of the replacement passed on 2026-11-11. The helper reported coordinator-local archival on publication.
- [x] Validate [production certificate initialization and recovery](trust-kms-cloudflare.md#production-certificate-provisioning-and-recovery). Production initialization and recovery with system-trust verification passed on 2026-11-11; recovery reused the existing certificate and published no unchanged state. Actual due renewal remains unverified.
- [x] Validate [process-lifetime TLS authorization and the locked listener](#authorize-and-verify-the-locked-tls-listener). Verified on `ups-aux` on 2026-11-11.
- [ ] Implement scheduled renewal/reload and integration of process-lifetime DNS/ACME authorization.
- [ ] Implement workstation/YubiKey authorization over SSH under the [session policy](../security/coordinator-sessions.md).
- [ ] Verify startup without Trust/OpenBao, the one-hour KMS window, expiry/lock/restart behaviour, and certificate renewal.

## Prepare Cloudflare and rehearse ACME

Follow the [standalone Cloudflare configuration guide](trust-kms-cloudflare.md)
to create the scoped DNS token and exercise Certbot issuance and renewal in RAM.

Operator results (2026-11-10): the dedicated `homelab-ups-aux-dns` token was
created with DNS Edit access to `simlun.se`, wrapped and committed in the private
records repository, and the parent submodule pointer updated. The
`kms-acme-tools` play completed with `ok=7`, `changed=4`, and no failures. With
contact email `acme@simlun.se`, the first attempt completed staging issuance but
failed during renewal. After the correction in
[PR #23](https://github.com/simlun-ai/homelab/pull/23), the operator reran the
rehearsal successfully: issuance and renewal retained the same TLS key, and the
disposable RAM workspace was removed. A subsequent TXT query to `1.1.1.1` for
`_acme-challenge.kms.k8s-aux.simlun.se` returned no records. This verifies the
staging rehearsal; durable wrapped ACME state recovery, production renewal and
the TLS listener were pending at that point.

Coordinator-local checks (2026-11-11): the updated tools play completed with
`ok=11`, `changed=3`, `unreachable=0`, `failed=0`. The operator imported the
existing wrapped staging record after YubiKey verification; the helper reported
that local files were unchanged. Default recovery then fetched the Pi's
ciphertext, recovered the staging state and DNS token, renewed successfully,
wrapped and independently recovered the update, and published it back to the
coordinator. The helper reported local archival of the previous ciphertext.
The operator then explicitly recreated staging state and recovered/renewed the
replacement successfully. Both operations reported verified ciphertext
publication and archival on the Pi. **The full coordinator-local staging
lifecycle passed.** Production issuance, the renewal timer and the TLS listener
remain pending.

Production attempt (2026-11-11): tools installation passed (`ok=11`, `changed=3`,
no failures); initialization then failed after the issuance progress message and
before wrapped publication. The [production guide](trust-kms-cloudflare.md#production-certificate-provisioning-and-recovery)
records the reproduced native renewal-file parser defect and reinstall/retry
instructions. The corrected-helper acceptance follows below; the timer and TLS
listener remain pending.

Production follow-up (2026-11-11): after the parser fix, the tools play passed
with `ok=11`, `changed=1`, `unreachable=0`, `failed=0`. Production initialization
verified the certificate name, matching key, validity and system-trusted chain,
then wrapped and independently recovered the state before storing its ciphertext
on the Pi. Default production recovery passed the same checks, reused the
existing certificate because renewal was not due, and reported no state changes
to publish. **Production initialization and certificate-reuse recovery passed.**
Actual production renewal and scheduled renewal/reload remain pending.

## Stage the locked service

After base hardening and SSH setup, run the dedicated play from the workstation:

```sh
make -C support/ups kms-stage HOST=ups-aux
```

The play uses the coordinator's Debian `python3-cryptography` package, installs
root-owned code, and enables `trust-kms.service` under a dedicated service
account. It verifies the installed unit with `systemd-analyze verify` and
requires the local status check to report a clean locked start.

To repeat the status check on the coordinator:

```sh
sudo /usr/bin/python3 -I -B /usr/local/lib/trust-kms/trust_kms_service.py status
```

Expect `state: locked`, a daemon instance ID, and `listener: disabled`.
On 2026-11-09 the operator ran the staging play successfully on `ups-aux`.
See the [Trust experiment record](02-trust.md#experiment-record-and-acceptance-checks). The
original staging run verified the locked local socket. The later TLS
verification is recorded below.


## Authorize and verify the locked TLS listener

Verified on `ups-aux` on 2026-11-11, including restart, the expected failed
network check while TLS was disabled, and successful reauthorization. See the
[validation record](02-trust.md#locked-production-tls-verification-2026-11-11).
The TLS authorization leaves the node-key window locked.
A service restart starts locked with TLS disabled and requires fresh workstation
YubiKey authorization before accepting TCP connections.

From the homelab root, load the SSH identity, then update both code installations:

```sh
make -C support/ups kms-acme-tools HOST=ups-aux
make -C support/ups kms-stage HOST=ups-aux
make -C support/ups kms-tls-status HOST=ups-aux
```

The KMS play installs Debian's `python3-grpcio`, `python3-protobuf`, cryptography,
OpenSSL and CA bundle. The dedicated unit permits Internet sockets and only
`CAP_NET_BIND_SERVICE` for the fixed `10.10.0.5:443` listener. It retains its
filesystem/core restrictions. The shared nftables template allows TCP 443 on
`ups-aux` from the existing management networks (currently `192.168.254.0/24`)
and `trust-cp1`'s configured `10.10.0.10/32`, plus the existing loopback rule.
Other coordinators receive no KMS port rule. Reapplying normal hardening retains
this host-specific rule. This does not authenticate peers by UUID or IP; the
approved trusted-network boundary still applies. The Pi's temporary DHCP
maintenance address is not added to the allowlist.

Expect `kms_state: locked`, `tls_state: disabled`, and a daemon `instance` ID.
Then authorize TLS using the existing coordinator-local production record:

```sh
make -C support/ups kms-tls-authorize HOST=ups-aux ACME_EMAIL=acme@simlun.se
make -C support/ups kms-tls-status HOST=ups-aux
```

The workstation checks that TLS is disabled and KMS locked, captures the daemon
instance, and runs production recovery/verification with the existing due-only
renewal behavior. Changed state is wrapped/verified/published first; unchanged
state needs no new wrapping. The workstation extracts only the TLS key and full
chain from the authenticated production snapshot in memory and streams them
over verified SSH to the root TLS helper. No ACME account or DNS token is sent
to the daemon. The helper/daemon recheck memory policy, and the daemon verifies
key, name, validity and system trust using anonymous public-certificate memory
descriptors. It receives no raw HMAC response or wrapping key.

The separate `/run/trust-kms/tls.sock` uses bounded framing and peer-UID checks;
only root and the service UID may call it. It does not use the boot-window
activation schema. A stale daemon instance, invalid identity, already-active
TLS listener or unsafe swap fails closed. Authorization returns public status
only. If interrupted, inspect status: activation may already have succeeded.
There is no replacement/reload operation in this slice; restart and reauthorize
explicitly if TLS is already active.

After authorization expect `tls_state: active`, endpoint `10.10.0.5:443`, public
certificate fingerprint/expiry, and `kms_state: locked`. Verify from the
operator workstation on the allowed management network:

```sh
# Once if the pinned gRPC rehearsal dependencies are not already installed:
make -C support/hsm kms-rehearsal-tools
make -C support/ups kms-tls-check HOST=ups-aux
```

The check uses the normal hostname and system CA bundle, with no hostname or
trust override. It must report successful TLS validation and both Seal/Unseal
returning `FAILED_PRECONDITION` (KMS locked). Its UUID and payload are public test
values, not actual unlock material. A failure can indicate DNS, routing/firewall,
missing TLS authorization, certificate validity or unexpected unlocked state.

Finally, verify that process restart discards TLS authorization:

```sh
make -C support/ups kms-restart HOST=ups-aux
make -C support/ups kms-tls-status HOST=ups-aux
```

Expect a new daemon instance, TLS disabled, and KMS locked. The TCP listener
must no longer be available. Reauthorize and rerun `kms-tls-check` to finish with
the verified listener active. The daemon closes TLS when certificate validity
ends or the clock moves before its validity window; renewal/reload remains a
later slice. All TLS secret material stays in process memory and is discarded
on restart/exit. The dedicated process disables dumping and rejects non-zram
swap or zram writeback before private-key acceptance; base hardening still applies.

Rollback: restart to drop in-memory TLS immediately. If reverting the feature,
restore the earlier code/unit and remove the `ups-aux` TCP-443 firewall entry,
then reapply hardening. Preserve coordinator-local ciphertext for later recovery;
no key or certificate recreation is required.

NUT and Prometheus exporter setup will extend the shared base runbook later.

References: [hardware](../inventory.md#shared-infrastructure), [coordinator layout](../layout.md#ups-shutdown-coordinators), [helper design](../security/helper-implementation.md), [wrapped-record deployment](../security/encrypted-record-storage.md#coordinator-deployment).


## Enable the disposable QEMU KMS policy

Use this only for the disposable Talos VM with system UUID
`5c73da99-dfe7-48b3-8687-5d0b46dbe647`. The UUID scopes the key policy;
it is a caller-supplied identifier, so the existing trusted-network boundary
still applies. The VM must use a virtual disk dedicated to the rehearsal.

Stage the updated service first with `make -C support/ups kms-stage HOST=ups-aux`.
On `ups-aux`, install a runtime-only systemd drop-in and restart:

```sh
sudo install -d -m 0755 /run/systemd/system/trust-kms.service.d
sudo tee /run/systemd/system/trust-kms.service.d/90-vm-rehearsal.conf >/dev/null <<'UNIT'
[Service]
ExecStart=
ExecStart=/usr/bin/python3 -I -B /usr/local/lib/trust-kms/trust_kms_service.py serve-locked --vm-rehearsal
UNIT
sudo systemctl daemon-reload
sudo systemctl restart trust-kms.service
```

From the workstation, run `kms-tls-authorize` as above to recover the
production TLS identity for the restarted service. Verify locked TLS with
`kms-tls-check`. When ready to create and reopen the VM's encrypted volume,
open the key window on `ups-aux`:

```sh
sudo /usr/bin/python3 -I -B /usr/local/lib/trust-kms/trust_kms_service.py vm-open
```

This generates one random key in memory and admits only the rehearsal UUID and
key ID. The supervisor limits the window to ten minutes. Complete both Seal and
the first reboot/Unseal during the same window. Locking, expiry or a service
restart discards the key. A later `vm-open` creates a different key, so start
over with a fresh virtual disk if the positive test needs to be repeated.

After the positive check, lock KMS on `ups-aux` and confirm a fresh VM boot
cannot unlock the encrypted volume while TLS still responds:

```sh
sudo /usr/bin/python3 -I -B /usr/local/lib/trust-kms/trust_kms_service.py vm-lock
```

The [QEMU rehearsal record](02-trust.md#native-talos-kms-rehearsal-in-qemu-2026-11-11)
captures the successful native unlock and the locked Unseal rejection.

Finish by removing the rehearsal override and restoring the normal locked unit:

```sh
sudo rm -f /run/systemd/system/trust-kms.service.d/90-vm-rehearsal.conf
sudo systemctl daemon-reload
sudo systemctl restart trust-kms.service
```

Reauthorize production TLS and rerun `kms-tls-check` if leaving the listener active.

## Enroll and authorize the Trust Pi KMS key

The public registration binds the observed `trust-cp1` UUID
`00d03115-0000-0000-1000-000089261f6e` to generation
`homelab/v1/trust/kms/trust-cp1/r1`. The VM override selects its separate
disposable policy. Pi enrollment, independent key recovery, coordinator staging, and the locked
TLS check passed on 2026-11-12. Authorization, explicit lock, and key reuse across two windows passed on
2026-11-14. See the [Trust validation record](02-trust.md#persistent-node-key-enrollment-2026-11-12).

With the Pi in maintenance mode at `10.10.0.246`, the private wrapped-record
submodule initialized, and the YubiKey connected, run from the workstation:

```sh
make -C clusters/trust kms-enroll
```

Enrollment verifies the live UUID, creates the 32-byte key once, and wraps it
in `secrets/wrapped/trust-cp1-kms-r1.json`. It then independently unwraps and
compares the recovered key. If the operation is interrupted after publication,
run `make -C clusters/trust kms-key-verify` to verify the existing record.
Review and commit the ciphertext in the private submodule and update the
parent pointer before installing any disk that depends on it. Keep the same
record for future boots and coordinator replacement.

Stage the updated coordinator service and reauthorize TLS after its restart.
With the coordinator SSH key loaded, use these workstation commands:

```sh
make -C clusters/trust kms-window-status
make -C clusters/trust kms-window-open
make -C clusters/trust kms-window-status
sealed_probe=$(make -s --no-print-directory -C clusters/trust kms-probe-seal)
make -C clusters/trust kms-window-lock
make -C support/ups kms-tls-check HOST=ups-aux
make -C clusters/trust kms-window-open
printf '%s\n' "$sealed_probe" | make -C clusters/trust kms-probe-unseal
make -C clusters/trust kms-window-lock
unset sealed_probe
```

The probe uses the gRPC dependencies from `make -C support/hsm kms-rehearsal-tools`.
It first checks rejection of an unregistered UUID, then seals a public payload.
Successful Unseal after reopening confirms that the same node key was recovered.
The workstation must be on an allowed management network.

Open requires the YubiKey to recover the enrolled record and sends the key over
host-verified SSH to the root helper. The request binds to the current daemon
instance and admits only the registered UUID and generation. The worker expires
after at most one hour. Explicit lock revokes the window and preserves TLS.
If an acknowledgment is lost, check status before retrying. To open again after
lock or expiry, recover the same record. The coordinator does not store it.

## Final follow-up: coordinator memory review

- [ ] Once the coordinator services are in place, review all homelab code that
  runs on `ups-aux` for memory leaks and unbounded growth. With swap disabled,
  soak-test the long-running services at idle and under repeated work. Include
  KMS authorization and worker teardown, certificate renewal and reload, and
  failure and retry paths. Track memory per service and for the whole host.
  Verify that usage stabilizes after repeated cycles and leaves headroom for
  concurrent services.
