# UPS coordinator base setup

**Base automation and hardening implemented; not yet tried on the Pis.** Repeat for each coordinator. This installs Raspberry Pi OS Lite on microSD and bootstraps Ansible management. NUT and a Prometheus exporter will be added later; only `ups-aux` continues to [step 01's additional Talos KMS setup](../docs/installation/01-main-coordinator.md).

Hardware/power assignments belong in the [inventory](../docs/inventory.md). Executable configuration and dependency pins live in [`support/ups/`](../support/ups/README.md).

## 1. Prepare the Ubuntu 26.04 workstation

Have the repository checked out, a microSD card and reader, and the operator's existing SSH key available. Use wired Ethernet, DHCP, and Internet access independent of the homelab clusters. Card models/capacities remain TBD.

From the repository root:

```sh
bash support/ups/install-system-dependencies.sh
make -C support/ups tools
make -C support/ups syntax
```

The installer uses sudo for workstation packages. Ansible runs locally in the scope's virtualenv; the Pis do not need an Ansible agent. Do not run `make tools` with sudo.

Download Raspberry Pi Imager for the workstation's architecture from [Raspberry Pi](https://www.raspberrypi.com/software/), make the AppImage executable, and launch it using the upstream Linux instructions.

## 2. Write each microSD card

Identify the card by comparing this output before and after insertion:

```sh
lsblk -o NAME,PATH,SIZE,MODEL,SERIAL,TRAN,MOUNTPOINTS
```

**Writing erases the selected device.** Check its identity and leave Imager's system-drive exclusion enabled.

In Imager:

1. Select **Raspberry Pi 3** and **Raspberry Pi OS Lite (64-bit)**. Use the same image for all three and record its release/date.
2. Select the microSD card.
3. Set hostname to `ups-aux` (Vault/Backup), `ups-pi`, or `ups-metal`, and username to **`administrator`**. Set timezone and keyboard layout.
4. Enable SSH with **public-key authentication only**, using the operator's existing `.pub` key. Leave Wi-Fi and Raspberry Pi Connect unconfigured.
5. Review, write, verify, and eject.

Never copy private keys onto the card or put credentials in the inventory or saved Imager presets. If the selected image requires an initial local-account password, follow the [secret-handling policy](../docs/security/security.md#secret-handling-boundary); SSH remains key-only. Validate the selected Imager/image's account setup on the first Pi.

## 3. First boot and trusted SSH access

Insert the card, connect Ethernet, and deliberately power on using its UPS-backed adapter. Wait for first-boot setup, find the address in DHCP leases, and create a reservation.

The [Ansible inventory](../support/ups/inventory.yaml) uses the three approved hostnames. Make them resolve through workstation DNS or existing SSH configuration. Alternatively, add a verified `ansible_host` address to the appropriate inventory entry. Management IPs remain unassigned in the repository.

Verify the SSH host-key fingerprint from a trusted local source. On the Pi's local console:

```sh
ssh-keygen -lf /etc/ssh/ssh_host_ed25519_key.pub
```

Alternatively, inspect that public-key file from its card after a clean shutdown. An unverified `ssh-keyscan` result alone does not establish identity.

Connect from the workstation, compare the fingerprint, and accept it only if it matches:

```sh
ssh administrator@ups-aux
```

Use the actual connection address if overriding `ansible_host`; repeat this trust step for each Pi. Confirm that the account can administer the Pi, then exit back to the workstation. Ansible will require an already trusted host key.

## 4. Bootstrap and verify one coordinator

From the repository root:

```sh
make -C support/ups inventory
make -C support/ups bootstrap HOST=ups-aux
make -C support/ups verify HOST=ups-aux
```

Bootstrap installs missing Python prerequisites, maintains the validated `administrator` passwordless sudo rule, and verifies SSH/Python, `aarch64`, and non-interactive root access. This grants full administration to the key-authenticated account. It does not reboot the host.

If the initial account requires a sudo password, bootstrap with an interactive prompt instead:

```sh
make -C support/ups bootstrap HOST=ups-aux ASK_BECOME_PASS=1
```

Use its existing initial sudo password; it is not saved in the repository or a file. If no working administrative access exists, correct the image/account setup first. Later runs use the normal passwordless command. The separate verification target performs no configuration changes.

Repeat with `HOST=ups-pi` and `HOST=ups-metal`. A missing, unknown, or multi-host selection is rejected. A second bootstrap on an unchanged host should report no changes.

## 5. Apply shared hardening

Run from a workstation address in `192.168.254.0/24`, after bootstrap:

```sh
make -C support/ups harden HOST=ups-aux
```

The [shared role](../support/ups/ansible/roles/coordinator_hardening/README.md) applies the [security policy](../docs/security/coordinator-hardening.md). It validates and reloads SSH/firewall configuration, enables automatic Debian security updates without automatic reboots, and configures memory and service restrictions. It owns the complete SSH and firewall configurations; KMS/NUT/exporter ports remain closed until explicitly added. There is no timed rollback.

After the first run or swap/radio changes, **reboot manually**, reconnect, and verify before supplying KMS secrets:

```sh
ssh administrator@ups-aux sudo systemctl reboot
make -C support/ups verify-hardening HOST=ups-aux
```

Wait for the host to return before running verification. Repeat one host at a time with `ups-pi` and `ups-metal`. Raspberry Pi vendor kernel/firmware updates remain separate manual maintenance. If access is lost, repair locally or reimage the card.

## 6. Record completion and recover from problems

Record the repository revision, Imager/image versions, workstation/Pi Python versions, Ansible version, host identity/address, and verification results. All three hosts remain **unverified** until tested.

- **No SSH:** check power, Ethernet, DHCP, name resolution, and first-boot completion.
- **Host-key mismatch after rebuilding:** verify the replacement fingerprint independently before removing the old known-hosts entry.
- **Ansible failure:** confirm SSH and administrative access, then Python compatibility and package access. Recreate the virtualenv with `make tools` if dependency verification fails.
- **Failed initial image:** rewrite the identified card and repeat. Preserve configuration and wrapped records before rebuilding an existing coordinator; base setup alone does not restore KMS or future UPS services.

Stop here with an Ansible-manageable base OS. NUT, exporter setup, and [shutdown/stay-off verification](../docs/layout.md#power-loss-shutdown-and-manual-startup) remain future work. Continue to [01 - Main coordinator](../docs/installation/01-main-coordinator.md) only for `ups-aux`.

## References

- [Raspberry Pi installation and Imager customisation](https://www.raspberrypi.com/documentation/computers/getting-started.html).
- [Ansible installation](https://docs.ansible.com/projects/ansible/latest/installation_guide/intro_installation.html).
- [Raw bootstrap module](https://docs.ansible.com/projects/ansible/latest/collections/ansible/builtin/raw_module.html).
