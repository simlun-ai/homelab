# Coordinator hardening

**Implemented in Ansible; not yet applied or verified on the Pis.**

The shared [role](../../support/ups/ansible/roles/coordinator_hardening/) applies to `ups-aux`, `ups-pi`, and `ups-metal`. The [base runbook](../../runbooks/ups-coordinator-base-setup.md) owns execution and verification.

- **SSH:** only `administrator`, public-key authentication, no direct root login or SSH forwarding. Preserve authorized keys and the approved passwordless sudo access.
- **Firewall:** nftables owns the complete host ruleset. Allow SSH from the management networks in [inventory.yaml](../../support/ups/inventory.yaml), initially `192.168.254.0/24`. Deny other inbound connections and forwarding, retaining loopback, established traffic, ICMP/IPv6, DHCP, and optional mDNS. Outbound traffic is allowed. KMS, NUT, and exporter allowances remain empty until their source addresses and ports are configured.
- **Updates:** daily automatic Debian security updates through unattended-upgrades, with automatic reboots explicitly disabled. Raspberry Pi's vendor archive is not separately security-classified; its kernel/firmware and other vendor updates remain manual maintenance. Package upgrades may restart services; if KMS loses its memory-held credentials, authorize it again from the workstation.
- **Memory:** no disk-backed swap, zram writeback, hibernation, or core dumps. Current Raspberry Pi OS is configured for RAM-only zram. Legacy swap startup is disabled. Swap and radio changes take effect after a manual reboot; verify before loading KMS secrets. This does not change the step 00 workstation policy.
- **Services/logs:** disable unused Bluetooth services and configure Wi-Fi/Bluetooth radios off for the wired hosts. Keep mDNS by default until independent name resolution is established. Bound persistent journal storage to 64 MB and seven days, with a 16 MB runtime limit. Do not log secret payloads.

Use ordinary Ansible templates and handlers with syntax validation; there is no timed rollback or automatic reboot. The role owns `/etc/ssh/sshd_config` and `/etc/nftables.conf`. Make deliberate changes through the repository. Future KMS/NUT/exporter service restrictions belong to those service roles.

References: [OpenSSH configuration](https://manpages.debian.org/trixie/openssh-server/sshd_config.5.en.html), [nftables](https://wiki.nftables.org/wiki-nftables/index.php/Simple_ruleset_for_a_server), [unattended-upgrades](https://sources.debian.org/src/unattended-upgrades/2.13/README.md), [Raspberry Pi swap configuration](https://github.com/raspberrypi/rpi-swap/blob/main/man/man5/swap.conf.5), [core dumps](https://www.freedesktop.org/software/systemd/man/coredump.conf.html).
