# UPS coordinator base setup

**`ups-aux` base setup verified on 2026-11-06. Bootstrap, hardening, and local console login with the wrapped administrator password all passed.** Repeat for each coordinator. This installs Raspberry Pi OS Lite on microSD and bootstraps Ansible management. NUT and a Prometheus exporter will be added later; only `ups-aux` continues to [step 01's additional Talos KMS setup](../docs/installation/01-main-coordinator.md).

Hardware/power assignments belong in the [inventory](../docs/inventory.md). Executable configuration and dependency pins live in [`support/ups/`](../support/ups/README.md).

## 1. Prepare the Ubuntu 22.04+ workstation

Have the repository checked out, a microSD card and reader, and a verified YubiKey available. Use wired Ethernet, DHCP, and Internet access independent of the homelab clusters. Card models/capacities remain TBD.

Use Python 3.13–3.14 for both the UPS and HSM helper environments. With pyenv
installed and initialized in your shell, the repository's `.python-version`
selects Python 3.13.18 for `make tools`. If it is not installed, first prepare pyenv's
[Python build dependencies](https://github.com/pyenv/pyenv/wiki#suggested-build-environment).

From the repository root, in the same shell:

```sh
bash support/ups/install-system-dependencies.sh
pyenv install -s 3.13.18
python3 --version
make -C support/ups tools
make -C support/ups syntax
```

The installer uses sudo for workstation packages; it does not upgrade the system Python.
The Makefiles use the selected `python3` to create their virtualenvs. Keep this
pyenv selection when following the SSH/password runbooks or rebuilding either
environment. An existing virtualenv created with another Python version must be
removed and recreated with `make tools`.
Ansible runs locally in the scope's virtualenv; the Pis do not need an Ansible agent. Do not run `make tools` with sudo.

Download Raspberry Pi Imager for the workstation's architecture from [Raspberry Pi](https://www.raspberrypi.com/software/), make the AppImage executable, and launch it using the upstream Linux instructions.

Before image preparation, generate and preserve the [shared wrapped SSH key](coordinator-ssh-key.md),
then create a separate wrapped administrator password per Pi using the
[password runbook](coordinator-passwords.md).

## 2. Write each microSD card

Identify the card by comparing this output before and after insertion:

```sh
lsblk -o NAME,PATH,SIZE,MODEL,SERIAL,TRAN,MOUNTPOINTS
```

**Writing erases the selected device.** Check its identity and leave Imager's system-drive exclusion enabled.

In Imager:

1. Select **Raspberry Pi 3** and **Raspberry Pi OS Lite (64-bit)**. Use the same image for all three and record its release/date.
2. Select the microSD card.
3. Set hostname to `ups-aux` (Trust/Backup), `ups-pi`, or `ups-metal`, and username to **`administrator`**. Set timezone and keyboard layout.
4. Enable SSH with **public-key authentication only**, using `support/ups/coordinator_ed25519.pub`. Leave Wi-Fi and Raspberry Pi Connect unconfigured.
5. Review, write, verify, and eject.

Never copy private keys onto the card or put credentials in the inventory or saved Imager presets. If the selected image requires an initial local-account password, use the [password runbook](coordinator-passwords.md#use-during-installation-or-recovery); SSH remains key-only. Validate the selected Imager/image's account setup on the first Pi.

## 3. First boot and trusted SSH access

Insert the card and connect Ethernet. For `ups-aux`, use an access port on
`k8s-aux` (VLAN 10). Power on using the UPS-backed adapter, wait for first-boot
setup, and find the initial address in the UniFi DHCP leases. On the Pi, run
`ip link show` and match the wired interface's `link/ether` address to the lease.
Record that MAC address for `ups-aux` in the [hardware inventory](../docs/inventory.md#shared-infrastructure).

Set a static address on `ups-aux` so it can reach the Talos nodes without a DHCP
lease. Use the Pi's local console because reactivating Ethernet can interrupt
remote access. See the [network overview](../docs/network.md) for allocations.

1. Run `nmcli device show` and note the IPv4 DNS servers (`IP4.DNS`) for the
   wired interface.
2. Run `sudo nmtui`. Select **Edit a connection**, open the active wired
   profile, and set **IPv4 CONFIGURATION** to **Manual**. Expand **Show**,
   set **Addresses** to `10.10.0.5/24` and **Gateway** to `10.10.0.1`, and enter
   the DNS servers from step 1. Enable **Automatically connect** and save.
3. Select **Activate a connection**. Deactivate the wired profile and activate
   it again to apply the new settings. Exit `nmtui`.

On the Pi, check for `10.10.0.5/24` on Ethernet, a default route via
`10.10.0.1`, and an IPv4 result from DNS.

```sh
ip -4 addr show
ip -4 route show default
getent ahostsv4 deb.debian.org
```

Use DHCP reservations for `ups-pi` and `ups-metal` during base setup. Their final
addresses are TBD.

The [Ansible inventory](../support/ups/inventory.yaml) and the password helper
connect to `ups-aux.k8s-aux.lundmark.internal`. From the workstation, verify
that it resolves to `10.10.0.5` with `getent ahostsv4 ups-aux.k8s-aux.lundmark.internal`.
Keep `HOST=ups-aux` for Make commands. Set up name resolution for `ups-pi` and
`ups-metal` once their addresses are known. An `ansible_host` override affects
Ansible only.

Verify the SSH host-key fingerprint from a trusted local source. On the Pi's local console:

```sh
ssh-keygen -lf /etc/ssh/ssh_host_ed25519_key.pub
```

Alternatively, inspect that public-key file from its card after a clean shutdown. An unverified `ssh-keyscan` result alone does not establish identity.

Load the shared key into your local agent as described in the [SSH key runbook](coordinator-ssh-key.md#load-before-management-operations). Connect from the workstation, compare the fingerprint, and accept it only if it matches:

```sh
ssh -o IdentitiesOnly=yes -i support/ups/coordinator_ed25519.pub administrator@ups-aux.k8s-aux.lundmark.internal
```

Use the actual connection address if overriding `ansible_host`; repeat this trust step for each Pi. Confirm that the account can administer the Pi, then exit back to the workstation. Ansible will require an already trusted host key.

## 4. Bootstrap and verify one coordinator

From the repository root:

```sh
make -C support/ups ssh-key-load
make -C support/ups inventory
make -C support/ups bootstrap HOST=ups-aux
make -C support/ups verify HOST=ups-aux
```

Bootstrap installs missing Python prerequisites, maintains the validated `administrator` passwordless sudo rule and the repository public key as its sole authorized key, and verifies SSH/Python, `aarch64`, and non-interactive root access. This grants full administration to the key-authenticated account. It does not reboot the host.

If the initial account requires a sudo password, bootstrap with an interactive prompt instead:

```sh
make -C support/ups bootstrap HOST=ups-aux ASK_BECOME_PASS=1
```

Use its existing initial sudo password; it is not saved in the repository or a file. If no working administrative access exists, correct the image/account setup first. Later runs use the normal passwordless command. The separate verification target performs no configuration changes.

Bootstrap sets `LOGIN_TIMEOUT 180` in `/etc/login.defs` to give the operator
three minutes to enter the wrapped administrator password at the local console.
The setting takes effect at the next console login.

Rerun bootstrap on an already hardened coordinator to apply this setting.
Bootstrap and hardening use the same ownership and permissions for the
administrator's SSH files. The hardening role owns the SSH daemon, firewall,
and other security settings separately.

Repeat with `HOST=ups-pi` and `HOST=ups-metal`. A missing, unknown, or multi-host selection is rejected. A second bootstrap on an unchanged host should report no changes.

## 5. Apply shared hardening

After bootstrap, run from a workstation address in `192.168.254.0/24`. For `ups-aux`, verify SSH access from that subnet to `10.10.0.5` through the UniFi gateway before applying hardening.

```sh
make -C support/ups harden HOST=ups-aux
```

The [shared role](../support/ups/ansible/roles/coordinator_hardening/README.md) applies the [security policy](../docs/security/coordinator-hardening.md). It validates and reloads SSH/firewall configuration, enables automatic Debian security updates without automatic reboots, and configures memory and service restrictions. It owns the complete SSH and firewall configurations; KMS/NUT/exporter ports remain closed until explicitly added. There is no timed rollback.

After the first run or swap/radio changes, **reboot manually**, reconnect, and verify before supplying KMS secrets:

```sh
ssh -o IdentitiesOnly=yes -i support/ups/coordinator_ed25519.pub administrator@ups-aux.k8s-aux.lundmark.internal sudo systemctl reboot
make -C support/ups verify-hardening HOST=ups-aux
```

Wait for the host to return before running verification. Repeat one host at a time with `ups-pi` and `ups-metal`. Raspberry Pi vendor kernel/firmware updates remain separate manual maintenance. If access is lost, repair locally or reimage the card.

After hardening verification, [apply the preserved wrapped password](coordinator-passwords.md#apply-to-an-existing-coordinator) to each Pi and verify local console login.

For routine updates to an already hardened coordinator, use the
[preview and apply targets](../support/ups/README.md#preview-and-apply-configuration)
to review and apply both configuration plays with diffs.

## 6. Record completion and recover from problems

Record the repository revision, Imager/image versions, workstation/Pi Python versions, Ansible version, host identity/address, and verification results.

- **No SSH:** check power, Ethernet, DHCP, name resolution, and first-boot completion.
- **Host-key mismatch after rebuilding:** verify the replacement fingerprint independently before removing the old known-hosts entry.
- **SSH key preflight fails:** from the repository root, run `ssh-add -T support/ups/coordinator_ed25519.pub` to check whether the current agent can sign with the key. If it fails, check the agent and run `make -C support/ups ssh-key-load` again.
- **Ansible failure:** confirm SSH and administrative access, then Python compatibility and package access. Recreate the virtualenv with `make tools` if dependency verification fails.
- **Failed initial image:** rewrite the identified card and repeat. Preserve configuration and wrapped records before rebuilding an existing coordinator; base setup alone does not restore KMS or future UPS services.

Stop here with an Ansible-manageable base OS. NUT, exporter setup, and [shutdown/stay-off verification](../docs/layout.md#power-loss-shutdown-and-manual-startup) remain future work. Continue to [01 - Main coordinator](../docs/installation/01-main-coordinator.md) only for `ups-aux`.

## References

- [Raspberry Pi installation and Imager customisation](https://www.raspberrypi.com/documentation/computers/getting-started.html).
- [Ansible installation](https://docs.ansible.com/projects/ansible/latest/installation_guide/intro_installation.html).
- [Raw bootstrap module](https://docs.ansible.com/projects/ansible/latest/collections/ansible/builtin/raw_module.html).
