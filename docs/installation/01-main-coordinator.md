# 01 - Main coordinator

**Placeholder; not yet implemented or verified.**

Prepare the Vault/Backup UPS coordinator and its independent Vault bootstrap KMS after [YubiKey setup](00-yubikey-setup.md).

## TODO

- [ ] Settle the host OS, network/time settings, and UPS shutdown configuration; document host preparation and independent SSH access.
- [ ] Implement the required Python helpers and Ansible provisioning under the planned scopes, including wrapped-record deployment, workstation/YubiKey authorization over SSH, KMS, and TLS/ACME handling.
- [ ] Verify startup without Vault/OpenBao, the one-hour KMS window, expiry/lock/restart behavior, certificate renewal, and independent UPS management.

References: [hardware](../inventory.md#shared-infrastructure), [coordinator layout](../layout.md#ups-shutdown-coordinators), [helper design](../security/helper-implementation.md), [session policy](../security/coordinator-sessions.md), [bootstrap KMS](../security/security.md#vault-bootstrap-kms).
