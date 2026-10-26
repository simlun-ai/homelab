#!/usr/bin/env python3
"""Read-only checks run on a coordinator after its manual reboot."""

import subprocess
import sys
from pathlib import Path

errors: list[str] = []


def check(condition: bool, message: str) -> None:
    if not condition:
        errors.append(message)


def output(*args: str) -> str:
    return subprocess.check_output(args, text=True).strip()


ssh = dict(line.split(" ", 1) for line in output("/usr/sbin/sshd", "-T").splitlines())
for key, expected in {
    "permitrootlogin": "no",
    "passwordauthentication": "no",
    "kbdinteractiveauthentication": "no",
    "authenticationmethods": "publickey",
    "disableforwarding": "yes",
    "allowusers": "administrator",
}.items():
    check(ssh.get(key) == expected, f"SSH {key} should be {expected}")

subprocess.run(["/usr/sbin/nft", "-c", "-f", "/etc/nftables.conf"], check=True)
firewall = output("/usr/sbin/nft", "list", "table", "inet", "coordinator")
check(firewall.count("policy drop;") >= 2, "Input and forwarding must default to drop")
check(bool(sys.argv[1:]), "No management networks supplied")
for network in sys.argv[1:]:
    check(
        f"{network} tcp dport 22 accept" in firewall,
        f"Management SSH rule missing: {network}",
    )
apt = output("apt-config", "dump")
for setting in (
    'Unattended-Upgrade::Automatic-Reboot "false";',
    'APT::Periodic::Update-Package-Lists "1";',
    'APT::Periodic::Unattended-Upgrade "1";',
):
    check(setting in apt, f"Missing effective APT setting: {setting}")
check("label=Debian-Security" in apt, "Security update origin is missing")
for timer in ("apt-daily.timer", "apt-daily-upgrade.timer"):
    subprocess.run(["systemctl", "is-enabled", "--quiet", timer], check=True)
    subprocess.run(["systemctl", "is-active", "--quiet", timer], check=True)

for line in Path("/proc/swaps").read_text().splitlines()[1:]:
    device = line.split()[0]
    check(device.startswith("/dev/zram"), f"Disk swap remains active: {device}")
for backing in Path("/sys/block").glob("zram*/backing_dev"):
    check(
        backing.read_text().strip() == "none",
        f"Zram writeback remains active: {backing}",
    )
check(
    Path("/proc/sys/kernel/core_pattern").read_text().strip() == "|/bin/false",
    "Core dumps are not disabled",
)
check(
    Path("/proc/sys/fs/suid_dumpable").read_text().strip() == "0",
    "Setuid core dumps are not disabled",
)
if errors:
    raise SystemExit(
        "\n".join(errors)
        + "\nReboot manually after initial hardening, then rerun this check."
    )
print(
    "SSH, firewall, automatic security updates and active memory protections verified."
)
if Path("/run/reboot-required").exists():
    print("Package updates request a manual reboot.")
