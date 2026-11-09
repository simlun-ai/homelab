# 01 - Main coordinator

**Draft; KMS implementation and hardware verification pending.**

First complete the shared [UPS coordinator base setup](../../runbooks/ups-coordinator-base-setup.md) for `ups-aux` at `10.10.0.5`, the Trust/Backup host. That runbook owns Raspberry Pi OS Lite installation, SSH access, and Ansible bootstrap for all three coordinators.

This step adds only Trust's independent Talos bootstrap KMS and its supporting TLS/ACME services. Complete [YubiKey setup](00-yubikey-setup.md) before authorizing KMS credentials.

## Additional KMS setup — TODO

The [draft Trust KMS contract](../security/trust-bootstrap-kms.md) records the
pinned Talos interface, proposed envelope/session protocol, open choices and
acceptance criteria. It is documentation, not a deployed or verified service.

- [x] Implement disposable software-only envelope/session tests for the approved behavior, with a fixed public vector. This verifies the envelope and session core.
- [x] Verify the [loopback gRPC-over-TLS rehearsal](../../support/hsm/README.md#trust-kms-loopback-rehearsal) on the operator workstation (Python 3.13.18, 2026-11-09).
- [x] Verify the [local authorization and worker rehearsal](../../support/hsm/README.md#trust-kms-loopback-rehearsal) on the operator workstation (three tests passed, 2026-11-09).
- [ ] Settle UUID mapping, early-boot NTP/networking, admission rules and independent recovery inputs. The public TLS endpoint is selected as `https://kms.k8s-aux.simlun.se:443`. The [UniFi DNS record](../network.md#required-dns-entries) resolved to `10.10.0.5` from the workstation and the Pi. The Pi's TCP probe timed out. Certificate and listener deployment remain pending.
- [ ] Configure independent DNS/time readiness for the coordinator and Trust under the [bootstrap KMS design](../security/security.md#trust-bootstrap-kms).
- [x] Stage the locked service on `ups-aux` and verify it reports an empty authorization window (2026-11-09).
- [ ] Run the [Certbot staging rehearsal](trust-kms-cloudflare.md#run-the-staging-rehearsal) on `ups-aux`.
- [ ] Implement durable wrapped ACME state recovery, scheduled production renewal and the locked TLS listener.
- [ ] Implement workstation/YubiKey authorization over SSH under the [session policy](../security/coordinator-sessions.md).
- [ ] Verify startup without Trust/OpenBao, the one-hour KMS window, expiry/lock/restart behaviour, and certificate renewal.

## Prepare Cloudflare and rehearse ACME

Follow the [standalone Cloudflare configuration guide](trust-kms-cloudflare.md)
to create the scoped DNS token and exercise Certbot issuance and renewal in RAM.

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
staged service has an empty key policy and rejects activation. It listens
only on the local Unix socket. Production TLS, remote admission, and
SSH/YubiKey delivery are separate acceptance checks.

NUT and Prometheus exporter setup will extend the shared base runbook later.

References: [hardware](../inventory.md#shared-infrastructure), [coordinator layout](../layout.md#ups-shutdown-coordinators), [helper design](../security/helper-implementation.md), [wrapped-record deployment](../security/encrypted-record-storage.md#coordinator-deployment).


## Final follow-up: coordinator memory review

- [ ] Once the coordinator services are in place, review all homelab code that
  runs on `ups-aux` for memory leaks and unbounded growth. With swap disabled,
  soak-test the long-running services at idle and under repeated work. Include
  KMS authorization and worker teardown, certificate renewal and reload, and
  failure and retry paths. Track memory per service and for the whole host.
  Verify that usage stabilizes after repeated cycles and leaves headroom for
  concurrent services.
