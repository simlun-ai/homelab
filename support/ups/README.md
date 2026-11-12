# UPS coordinator management

Shared base setup for `ups-aux` (Trust/Backup), `ups-pi`, and `ups-metal`.
Use the [runbook](../../runbooks/ups-coordinator-base-setup.md) for imaging,
SSH host identity, installation order, and recovery.

- `inventory.yaml`: coordinator selectors, connection names, and the
  `administrator` SSH account. `ups-aux` connects to
  `ups-aux.k8s-aux.lundmark.internal`. Connection names must resolve through
  DNS or existing SSH configuration. Keep private keys and passwords out of
  the inventory.
- `requirements.txt`: exact workstation dependency pins. `make tools` installs
  them into the ignored `.venv/`; all Ansible targets verify those pins.
- `ansible.cfg`: strict host-key checking, non-interactive SSH, memory-only facts.
- `ansible/playbooks/bootstrap.yaml`: Python prerequisites, validated sudo rule, sole repository authorized key,
  and base verification. `ASK_BECOME_PASS=1` prompts for an existing initial sudo
  password if necessary.
- `ansible/playbooks/verify.yaml`: read-only SSH/Python, architecture, and
  passwordless sudo checks. It does not install or repair anything.

- `ansible/roles/coordinator_hardening/`: shared SSH, nftables, automatic security
  updates without reboots, and memory/service restrictions; see the
  [policy](../../docs/security/coordinator-hardening.md).

Run `make -C support/ups help`. Bootstrap, hardening, and verification require exactly one
`HOST`; the playbooks also reject multi-host execution before connecting.
The base flow does not reboot hosts. NUT and exporters remain pending. Trust KMS
staging uses its own play and [coordinator runbook](../../docs/installation/01-main-coordinator.md#stage-the-locked-service).

Dependency selection: [ansible-core release](https://pypi.org/project/ansible-core/2.21.5/),
[Python compatibility](https://docs.ansible.com/projects/ansible/latest/reference_appendices/release_and_maintenance.html).
Ubuntu 22.04 or newer is the workstation target, with Python 3.13–3.14 selected
through pyenv as described in the runbook. Hardware installation remains unverified.

## Preview and apply configuration

For an existing coordinator with trusted SSH and working passwordless sudo:

```sh
make -C support/ups diff HOST=ups-aux
make -C support/ups apply HOST=ups-aux
```

Both run bootstrap and hardening in order. `diff` uses Ansible check mode and
shows diffs where modules support them. It expects an already provisioned
host because the preview cannot install prerequisites. `apply` runs the same
plays with diffs and checks access after applying changes. Follow the
[manual reboot and verification procedure](../../runbooks/ups-coordinator-base-setup.md#5-apply-shared-hardening)
when required.

## Static checks

From the repository root, run `make ansible-lint` for the pinned containerized
`safety` profile. It is also part of `make ci`; see the [CI instructions](../../ci/README.md).
These checks do not connect to coordinators. Operational inventory and playbook
syntax checks remain available through this scope's `inventory` and `syntax` targets.

## Administrator passwords

See the [password runbook](../../runbooks/coordinator-passwords.md) for
`password-create`, `password-reveal`, and `password-apply`, each with `HOST=...`.
These reuse `HSM_VENV` (default `~/.local/share/homelab/venvs/hsm`), installed by `make -C support/hsm tools`, and keep secrets out of Ansible. Use the same override for installation and consumers.

## Shared SSH identity

The [SSH key runbook](../../runbooks/coordinator-ssh-key.md) covers one-time
`ssh-key-create`, per-session `ssh-key-load`, and `ssh-key-unload`. Ansible
selects `coordinator_ed25519.pub` and requires its private half in the local
agent. Bootstrap replaces the administrator authorized keys with this one key;
follow the migration procedure before bootstrapping existing hosts.

Wrapped ACME staging state: `make -C support/ups kms-acme-state HOST=ups-aux ACME_EMAIL=...`
defaults to recovery. Use `ACME_STATE_MODE=init` once or explicitly select
`ACME_STATE_MODE=recreate` to issue replacement identity material and archive
existing ciphertext. See the [staging state instructions](../../docs/installation/trust-kms-cloudflare.md#wrapped-staging-state-initialize-recover-and-recreate).
ACME ciphertext and archives are stored only on the Pi. Use `ACME_STATE_MODE=import` with an absolute `ACME_IMPORT_RECORD` to move the previously tested record there without new issuance. The helper leaves local files untouched; no ACME Git commit is needed. Staging is the default; explicitly set `ACME_ENVIRONMENT=production` for production state. Production initialization and certificate-reuse recovery with system-trust verification passed on 2026-11-11; listener integration is verified and actual renewal/expiry remains pending. See the [production instructions](../../docs/installation/trust-kms-cloudflare.md#production-certificate-provisioning-and-recovery).


## Locked KMS TLS listener

Reapply `kms-stage HOST=ups-aux` to install the TLS control helper, service
runtime/network permissions and scoped host firewall rule. It starts locked
with TLS disabled. `kms-tls-authorize HOST=ups-aux ACME_EMAIL=...` recovers only
the existing production identity and explicitly activates TLS; `kms-tls-status`
reports public state, `kms-tls-check` verifies trusted TLS and locked RPCs from
the management workstation, and `kms-restart` discards in-memory authorization.
The check requires the pinned `support/hsm kms-rehearsal-tools` dependencies.
Follow the [complete validation sequence](../../docs/installation/01-main-coordinator.md#authorize-and-verify-the-locked-tls-listener).
Deployment, workstation TLS checks, restart and reauthorization passed on
`ups-aux` on 2026-11-11. For Pi key enrollment and authorization, see the [coordinator runbook](../../docs/installation/01-main-coordinator.md#enroll-and-authorize-the-trust-pi-kms-key). Automatic renewal/reload remains pending.
