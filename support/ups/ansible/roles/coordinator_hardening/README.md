# coordinator_hardening

Apply after base bootstrap with `make -C support/ups harden HOST=ups-aux`.
Use the [base runbook](../../../../../runbooks/ups-coordinator-base-setup.md) for the
manual reboot and verification. [Security policy](../../../../../docs/security/coordinator-hardening.md)
owns the intended behaviour. Hardware verification is pending.

| Variable | Purpose |
| --- | --- |
| `coordinator_hardening_management_networks` | Required SSH source CIDRs, assigned in the UPS inventory. |
| `coordinator_hardening_firewall_services` | Additional source-scoped rules, empty by default. Each entry has `sources` (CIDRs), `protocol` (`tcp` or `udp`), and `port`. |
| `coordinator_hardening_disable_radios` | Default true; disable Bluetooth services and stage boot overlays for wired operation. |
| `coordinator_hardening_disable_mdns` | Default false; preserve mDNS until DNS/SSH aliases work independently. |

This role manages the entire SSH server configuration and nftables ruleset.
No KMS, NUT, or exporter ports are opened automatically. OS packages follow
the configured distribution repositories; exact installed versions are recorded
during hardware verification.

On current Raspberry Pi OS, RAM-only zram is selected through `rpi-swap`.
On older images using dphys-swapfile, swap startup is disabled instead.
A manual reboot is required after initial swap/radio configuration; live swap is
not reconfigured under memory pressure. The verification command rejects disk
swap or zram writeback still active after boot.
