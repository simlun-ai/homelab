# 01 - Main coordinator

**Draft; KMS implementation and hardware verification pending.**

First complete the shared [UPS coordinator base setup](../../runbooks/ups-coordinator-base-setup.md) for `ups-aux`, the Vault/Backup host. That runbook owns Raspberry Pi OS Lite installation, SSH access, and Ansible bootstrap for all three coordinators.

This step adds only Vault's independent Talos bootstrap KMS and its supporting TLS/ACME services. Complete [YubiKey setup](00-yubikey-setup.md) before authorizing KMS credentials.

## Additional KMS setup — TODO

- [ ] Configure independent DNS/time readiness for the coordinator and Vault under the [bootstrap KMS design](../security/security.md#vault-bootstrap-kms).
- [ ] Implement the Python helpers and Ansible configuration for KMS, TLS/ACME, and local wrapped-record deployment.
- [ ] Implement workstation/YubiKey authorization over SSH under the [session policy](../security/coordinator-sessions.md).
- [ ] Verify startup without Vault/OpenBao, the one-hour KMS window, expiry/lock/restart behaviour, and certificate renewal.

Detailed commands will be added as this setup is implemented. NUT and Prometheus exporter setup will extend the shared base runbook later.

References: [hardware](../inventory.md#shared-infrastructure), [coordinator layout](../layout.md#ups-shutdown-coordinators), [helper design](../security/helper-implementation.md), [wrapped-record deployment](../security/encrypted-record-storage.md#coordinator-deployment).

