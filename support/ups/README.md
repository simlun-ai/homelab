# UPS coordinator management

Shared base setup for `ups-aux` (Vault/Backup), `ups-pi`, and `ups-metal`.
Use the [runbook](../../runbooks/ups-coordinator-base-setup.md) for imaging,
SSH host identity, installation order, and recovery.

- `inventory.yaml`: hostnames and `administrator` SSH account. Names must resolve
  through DNS or existing SSH configuration; add verified `ansible_host` addresses
  here if needed. No private keys or passwords.
- `requirements.txt`: exact workstation dependency pins. `make tools` installs
  them into the ignored `.venv/`; all Ansible targets verify those pins.
- `ansible.cfg`: strict host-key checking, non-interactive SSH, memory-only facts.
- `ansible/playbooks/bootstrap.yaml`: Python prerequisites, validated sudo rule,
  and base verification. `ASK_BECOME_PASS=1` prompts for an existing initial sudo
  password if necessary.
- `ansible/playbooks/verify.yaml`: read-only SSH/Python, architecture, and
  passwordless sudo checks. It does not install or repair anything.

Run `make -C support/ups help`. Bootstrap and verification require exactly one
`HOST`; the playbooks also reject multi-host execution before connecting.
The base flow does not reboot hosts. KMS, NUT, and exporters remain unimplemented.

Dependency selection: [ansible-core release](https://pypi.org/project/ansible-core/2.21.5/),
[Python compatibility](https://docs.ansible.com/projects/ansible/latest/reference_appendices/release_and_maintenance.html).
Ubuntu 26.04 is the workstation target; hardware installation remains unverified.
