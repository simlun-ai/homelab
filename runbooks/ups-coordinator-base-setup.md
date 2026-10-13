# UPS coordinator base setup

**Draft; not yet tried on hardware.** Repeat for each of the three coordinators. This runbook covers Raspberry Pi OS Lite on microSD, SSH access, and Ansible bootstrap. NUT and a Prometheus exporter will be added later. Only the Vault/Backup coordinator continues to [step 01's additional Talos KMS setup](../docs/installation/01-main-coordinator.md).

Hardware and UPS power assignments belong in the [inventory](../docs/inventory.md); configuration belongs under [`support/ups/`](../docs/layout.md#ups-shutdown-coordinators).

## 1. Prepare the Linux workstation

Have the repository checked out, an SD-card reader, one microSD card per coordinator, and the operator's existing SSH key available. Use wired Ethernet for this draft, with DHCP and Internet access independent of the homelab clusters. Size each card for the selected Lite image; card models/capacities remain TBD.

On a Debian/Ubuntu workstation:

```sh
sudo apt update
sudo apt install openssh-client python3 python3-venv
```

On another Linux distribution, install the equivalent packages.

Download Raspberry Pi Imager for the workstation's architecture from [Raspberry Pi](https://www.raspberrypi.com/software/). Make the downloaded AppImage executable and launch it according to the upstream Linux instructions. Record its version.

Choose distinct hostnames and an administrative username before writing cards. Suggested names, not assigned network identities:

| Coordinator | Proposed hostname |
| --- | --- |
| Vault/Backup | `ups-vault-backup` |
| Pi | `ups-pi` |
| Metal | `ups-metal` |

Record the chosen names, Ethernet MAC addresses, and management addresses in the UPS inventory as each host comes online. Use DHCP reservations for stable addresses in this draft.

## 2. Write each microSD card

Identify the card before selecting it in Imager:

```sh
lsblk -o NAME,PATH,SIZE,MODEL,SERIAL,TRAN,MOUNTPOINTS
```

Compare the device list before and after inserting the card. **Writing erases the selected device.** Check its identity and leave Imager's system-drive exclusion enabled.

In Imager:

1. Select **Raspberry Pi 3** and **Raspberry Pi OS Lite**. This draft proposes the **64-bit** image; record the exact release/date and architecture used, and use the same image for all three.
2. Select the microSD card.
3. Set its unique hostname, administrative username, timezone, and keyboard layout.
4. Enable SSH with **public-key authentication only**, using the operator's existing `.pub` key. Never copy the private key onto the card. Leave Wi-Fi and Raspberry Pi Connect unconfigured.
5. Review, write, and allow verification to complete. Eject the card.

Image/Imager versions and their passwordless account/sudo behaviour must be verified on the first Pi before repeating the setup. Do not put account passwords or private keys in repository files or saved Imager presets; follow the [secret-handling policy](../docs/security/security.md#secret-handling-boundary) if the selected image requires a bootstrap credential.

## 3. First boot and SSH

Insert the card, connect Ethernet, and deliberately power on using the [UPS-backed adapter](../docs/inventory.md). Allow first-boot configuration to finish. Find the address in the router's DHCP leases and create its reservation.

Verify the SSH host-key fingerprint through a trusted local source before accepting it. For example, on the Pi's local console:

```sh
ssh-keygen -lf /etc/ssh/ssh_host_ed25519_key.pub
```

Alternatively, read that public-key file from the Pi's card on the workstation after a clean shutdown. An unverified `ssh-keyscan` result alone does not establish identity.

On the workstation, substitute the actual username/address:

```sh
COORDINATOR_USER='<admin-user>'
COORDINATOR_ADDR='<management-address>'
ssh "${COORDINATOR_USER}@${COORDINATOR_ADDR}"
```

Compare the first-connection fingerprint with the trusted value. Keep host-key checking enabled.

Inside the SSH session:

```sh
hostnamectl
cat /etc/os-release
uname -m
sudo -n true
```

Expect the chosen hostname, Raspberry Pi OS, `aarch64` for the proposed image, and successful non-interactive sudo. The draft uses the operator's key-authenticated administrative account for Ansible.

If sudo requires a password, use existing authorized administrative access to run `sudo visudo -f /etc/sudoers.d/010-homelab-admin` on the Pi. Add the following, replacing `ADMIN_USER` with the real username:

```sudoers
ADMIN_USER ALL=(ALL:ALL) NOPASSWD: ALL
```

Validate with `sudo visudo -c`, then repeat `sudo -n true` in a second SSH session before closing the first. This grants full administration to that SSH account. If no working administrative access exists, correct the image/account setup rather than bypassing authentication.

Exit to the workstation. All remaining commands run there.

## 4. Bootstrap Ansible on the workstation

Ansible runs on the workstation; the Pis need SSH, sudo, and Python, with no Ansible agent.

From the repository root, use a dedicated virtualenv. Before executing, select an exact `ansible-core` version compatible with both the workstation Python and the Pi's Python using the [upstream support matrix](https://docs.ansible.com/projects/ansible/latest/reference_appendices/release_and_maintenance.html). The pin is **TBD**; record it in the UPS scope's planned `toolchain.yaml` when implementing this step.

```sh
ANSIBLE_CORE_VERSION='<exact-compatible-version>'
mkdir -p support/ups
python3 -m venv support/ups/.venv
support/ups/.venv/bin/python -m pip install "ansible-core==${ANSIBLE_CORE_VERSION}"
support/ups/.venv/bin/ansible --version
```

Ignore `support/ups/.venv/` in Git before running these commands. Use its executables explicitly; the eventual scoped Make/bin entry points remain to be implemented.

## 5. Inventory and target bootstrap

Create `support/ups/inventory.yaml` with real addresses and the username configured in Imager. The following is a template; replace every placeholder and adjust aliases if different hostnames were chosen.

```yaml
all:
  children:
    ups_coordinators:
      vars:
        ansible_user: REPLACE_WITH_ADMIN_USER
        ansible_python_interpreter: /usr/bin/python3
      hosts:
        ups-vault-backup:
          ansible_host: REPLACE_WITH_VAULT_BACKUP_ADDRESS
        ups-pi:
          ansible_host: REPLACE_WITH_PI_ADDRESS
        ups-metal:
          ansible_host: REPLACE_WITH_METAL_ADDRESS
```

Use the existing SSH agent or SSH configuration for key selection; keep credentials out of the inventory. Verify each host's SSH identity as above before managing it.

Select only the coordinator currently being prepared:

```sh
COORDINATOR='ups-vault-backup'
support/ups/.venv/bin/ansible-inventory -i support/ups/inventory.yaml --graph
support/ups/.venv/bin/ansible ups_coordinators -i support/ups/inventory.yaml \
  --limit "$COORDINATOR" --list-hosts
```

Confirm exactly one intended host is selected. Bootstrap Python through the raw module, which does not require Python on the target:

```sh
support/ups/.venv/bin/ansible ups_coordinators -i support/ups/inventory.yaml \
  --limit "$COORDINATOR" --become -m ansible.builtin.raw \
  -a 'apt-get update && apt-get install -y python3 python3-apt'
```

Verify normal module execution and privilege escalation:

```sh
support/ups/.venv/bin/ansible ups_coordinators -i support/ups/inventory.yaml \
  --limit "$COORDINATOR" -m ansible.builtin.ping
support/ups/.venv/bin/ansible ups_coordinators -i support/ups/inventory.yaml \
  --limit "$COORDINATOR" --become -m ansible.builtin.command -a 'id -u'
```

Expect `pong` and UID `0`. Repeat for the other two hosts when ready.

## 6. Record completion and recover from problems

Record the repository revision, Imager/image versions, workstation/Pi Python versions, Ansible pin, host identity/address, and SSH/Ansible verification results. All three hosts are currently **unverified**.

- **No SSH:** check power, Ethernet, DHCP, and first-boot completion; inspect locally before rewriting the card.
- **Host-key mismatch after rebuilding:** verify the new fingerprint independently before removing the old known-hosts entry.
- **Ansible failure:** confirm ordinary SSH and sudo first, then Python-version compatibility and package access.
- **Failed initial image:** rewrite the identified card and repeat. For an existing coordinator, preserve its required configuration and wrapped records before rebuilding; base setup alone does not restore KMS or future UPS services.

Stop here with an Ansible-manageable base OS. NUT, exporter configuration, and verification of [shutdown/stay-off behaviour](../docs/layout.md#power-loss-shutdown-and-manual-startup) remain future work. Continue to [01 - Main coordinator](../docs/installation/01-main-coordinator.md) only for Vault/Backup's additional KMS services.

## References

- [Raspberry Pi installation and Imager customisation](https://www.raspberrypi.com/documentation/computers/getting-started.html).
- [Ansible installation](https://docs.ansible.com/projects/ansible/latest/installation_guide/intro_installation.html).
- [Ansible raw bootstrap module](https://docs.ansible.com/projects/ansible/latest/collections/ansible/builtin/raw_module.html).
- [Ansible connectivity/Python check](https://docs.ansible.com/projects/ansible/latest/collections/ansible/builtin/ping_module.html).
