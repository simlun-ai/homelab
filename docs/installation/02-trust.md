# 02 - Trust

## Working roadmap: encrypted Talos and Kubernetes bootstrap

**Primary milestone:** Install `trust-cp1` as an encrypted Talos single-node Kubernetes cluster on `k8s-aux` (VLAN 10), with system-volume unlock provided by the independent KMS on `ups-aux`. This is the initial installation, **not** a disposable unencrypted bootstrap. OpenBao and other application workloads are later milestones.

**Working branch:** `feat/trust-bootstrap`. Work in small, reviewable commits on this branch. Before each change, agree on the next decision, implement only that slice, test it where possible, and update this roadmap with evidence. Do not mark physical tests complete from configuration or documentation alone.

### Current position

- **Completed prerequisite:** `ups-aux` base bootstrap/hardening and console login verified (2026-11-06). Its additional KMS service is not yet implemented.
- **Decided identity:** cluster `trust`, control-plane node `trust-cp1`, FQDN `trust-cp1.k8s-aux.lundmark.internal`, static IP `10.10.0.10/24`; coordinator `ups-aux` at `10.10.0.5`.
- **Planned, not verified:** Pi 4 UEFI firmware-card boot, Talos installation, OS SSD MD RAID1, KMS-backed `STATE`/`EPHEMERAL` encryption, and Kubernetes bootstrap.
- **Current next step:** Agree on the Trust provisioning layout, the minimal cluster-scope tooling/version pins, and how configuration and secret material will be generated and handled. Do not install onto disks yet.

### Milestone tracker

| # | Stage | Exit criteria | Status |
| --- | --- | --- | --- |
| 0 | Identity and working baseline | Names/IP/roles and owning files agree; branch and roadmap established | In progress — baseline recorded; branch created |
| 1 | Provisioning contract and scoped tools | Agree on declarative node/disk schema, `clusters/trust/` layout, version pins, `make` entry points and safe secret-handling approach; implement the minimum needed | Pending |
| 2 | KMS protocol and recovery decisions | Specify per-node wrapped key context, seal/unseal envelope, TLS endpoint and certificate handling, session authorization, early boot DNS/NTP, admission restrictions, and independent loss recovery | Pending |
| 3 | `ups-aux` KMS implementation | Service and Ansible configuration deployed; authorized `Seal`/`Unseal`, expiry, restart and fail-closed checks verified independently of Kubernetes/OpenBao | Pending |
| 4 | Pi 4 UEFI live-boot experiment | EDK2 card cold-boots; generic ARM64 Talos installer sees Ethernet, memory and explicitly identified disks; evidence recorded below | Pending |
| 5 | OS storage and machine configuration | Confirm supported bootable MD RAID1 path, immutable disk selectors, pre-`STATE` networking and KMS-backed `STATE`/`EPHEMERAL` settings; validate before destructive actions | Pending |
| 6 | Install encrypted Talos | Deliberately install onto assigned OS disks only; cold boot with the independent KMS authorized; encrypted volume coverage verified | Pending |
| 7 | Bootstrap Kubernetes | Bootstrap the single control-plane node; verify API, node readiness, system pods, DNS and Flannel networking | Pending |
| 8 | Recovery and repeatability | Verify KMS locked/unlocked cold boots, expiry and failure modes, OS mirror degraded boot/recovery, and documented reproducible rebuild | Pending |

**Milestone boundary:** Stage 7 is the first target. Do not expand into OpenBao, ZFS LocalPV, ingress, certificates, monitoring, backups or the dependent-cluster KMS adapter until the basic encrypted Trust cluster is working. Stage 8 validates that milestone's recovery characteristics before treating the installation as production-ready.

### Decisions to settle as we go

| Topic | Current direction / unresolved question |
| --- | --- |
| Cluster and node identity | `trust` / `trust-cp1` agreed; stable Kubernetes API DNS name and endpoint choice TBD |
| Networking | VLAN 10, `10.10.0.10/24`, gateway `10.10.0.1`; current proposed pod/service CIDRs and Flannel are in [network.md](../network.md). Pre-`STATE` DNS and NTP details TBD |
| Provisioning | Prefer reproducible, scoped `clusters/trust/` Make/toolchain/configuration, per [layout.md](../layout.md); concrete node schema, pin values and generation workflow TBD |
| Boot | First experiment is SD-first EDK2/UEFI plus generic ARM64 Talos installer; supported behavior and firmware boot dependency must be verified |
| Storage | Two explicitly assigned OS SSDs are intended for MD RAID1; confirm stable identities, Talos compatibility, metadata format, degraded boot and replacement before any destructive installation. Separate encrypted ZFS data disks are **out of scope and protected** |
| Encryption | KMS-backed `STATE` and `EPHEMERAL` on the **initial** installation. Talos bootloader/kernel still require readable boot components; no claim of fully encrypted boot media |
| KMS | Dedicated coordinator service on `ups-aux`, independent of Trust and OpenBao; YubiKey-authorized one-hour key window, TLS and encrypted wrapped records per [security policy](../security/security.md#trust-bootstrap-kms). Precise service and recovery contract TBD |
| Secret handling | Never write plaintext Talos machine secrets, talosconfig, kubeconfig, KMS keys or unsealed material to workstation disk. Final generation/transport/bootstrap workflow TBD |

### Step-by-step working rules

1. Choose **one** pending decision or test; document any preconditions before implementation.
2. Add only the files, commands and checks needed for that step; keep all affected documentation synchronized.
3. Record the relevant commit/revision, selected versions, host/disk identities, real observations and failure/recovery notes **without secret output**.
4. Check a milestone only when its exit criteria have been verified; leave unsuccessful experiments and revised decisions visible.
5. Before running any destructive storage operation, positively identify targets and explicitly exclude the separate Trust data mirror. Never infer a safe disk from `/dev/sdX`, size or apparent emptiness alone.

### Progress log

| Date | Milestone | Evidence / decision | Next action |
| --- | --- | --- | --- |
| 2026-11-06 | 0 — baseline | Started `feat/trust-bootstrap` after the Trust rename; accepted `trust-cp1` and `10.10.0.10`. `ups-aux` base setup previously verified. No Trust disk or KMS tests performed | Review provisioning layout and pinning strategy |

---

**Installation in progress; hardware steps and KMS remain unverified until explicitly recorded below.**

Install the independent Trust cluster after the [main coordinator](01-main-coordinator.md) is ready. Firmware-card preparation can be tried separately while the coordinator/KMS work is pending.

Use `10.10.0.10/24` with gateway `10.10.0.1` on `k8s-aux` (VLAN 10) for the installed `trust-cp1` node (`trust-cp1.k8s-aux.lundmark.internal`). Plan for this address to be available before Talos loads encrypted `STATE`, so the node can reach the coordinator's KMS on `10.10.0.5`. The preboot configuration and KMS endpoint are still TBD. See the [network overview](../network.md) for the Trust load balancer pool and proposed Kubernetes CIDRs.

## First installation experiment: Pi 4 UEFI

The first method to try is [pftf/RPi4](https://github.com/pftf/RPi4) firmware on a dedicated microSD card, booting a generic Talos ARM64 installer from USB and installing onto the assigned OS SSD mirror. This is a candidate installation method, not a settled design or a verified supported combination.

The SD card remains inserted for normal operation and is a boot dependency outside the SSD mirror. Keep all disk operations below confined to the firmware card; the [Trust data disks](../inventory.md#trust) are not installation targets.

This experiment aims to avoid the modified raw-image/META deletion and manual firmware-copy workaround described in [Talos issue #14555](https://github.com/siderolabs/talos/issues/14555#issuecomment-6464577848). Successful UEFI boot reports exist, but do not establish that our ISO installation, RAID1 failover, upgrades, or KMS unlock work.

### Prepare SD-first EEPROM boot

The Pi EEPROM bootloader must select SD before USB so that EDK2 runs before the SSD bootloader. EEPROM boot order and EDK2's subsequent OS boot order are separate settings.

If SD-first boot is already configured, skip this step. Otherwise, on the workstation, use Raspberry Pi Imager with a spare card:

1. Select Raspberry Pi 4, then **Misc utility images → Bootloader → SD Card Boot**.
2. Write the recovery card.
3. Power off the Pi, disconnect USB disks, insert the recovery card, and power on.
4. Wait for a green HDMI screen and a steadily flashing activity LED.
5. Power off and remove the card.

This resets the EEPROM bootloader configuration. The recovery card may then be reformatted for UEFI below. See the [Raspberry Pi bootloader recovery instructions](https://www.raspberrypi.com/documentation/computers/raspberry-pi.html#reflash-the-bootloader).

### Download firmware on the Linux workstation

Use the release ZIP, not GitHub's source archive. Version 1.53 is the initial experiment pin; revisit it deliberately when recording results.

```bash
curl -fL -o RPi4_UEFI_Firmware_v1.53.zip \
  https://github.com/pftf/RPi4/releases/download/v1.53/RPi4_UEFI_Firmware_v1.53.zip

echo 'ca9973e2a7a546b3df871cfb7382e656829114b6dfa424f40dc67cc90a217d88  RPi4_UEFI_Firmware_v1.53.zip' \
  | sha256sum --check
```

The checksum comes from the [release asset metadata](https://api.github.com/repos/pftf/RPi4/releases/tags/v1.53) checked on 2026-10-28; proceed only if verification succeeds.

### Partition and populate the firmware card

Requires Linux tools: `curl`, `sha256sum`, `lsblk`, `sfdisk`, `partprobe`, `udevadm`, `mkfs.vfat`, `mount`, and `unzip`.

**The partitioning and formatting commands erase the selected card.** Identify it by model and size, and unmount every mounted partition on that card before continuing:

```bash
lsblk -p -o NAME,SIZE,MODEL,TRAN,FSTYPE,MOUNTPOINTS
```

Replace both placeholders with the whole SD device and its first partition. For a built-in reader, these may be `/dev/mmcblk0` and `/dev/mmcblk0p1`.

```bash
sd_device=/dev/sdX
sd_partition=/dev/sdX1
```

Run these blocks one at a time, stopping on any error. Create an MBR table with a 512 MiB FAT32 partition of type `0xef`, following the [pftf preparation instructions](https://github.com/pftf/RPi4#installation):

```bash
sudo sfdisk --wipe always "$sd_device" <<'EOF'
label: dos
start=2048, size=1048576, type=ef
EOF

sudo partprobe "$sd_device"
sudo udevadm settle
sudo mkfs.vfat -F 32 -n PIUEFI "$sd_partition"
```

Extract the complete archive at the root of the FAT partition:

```bash
mkdir -p pi-uefi-mount
sudo mount "$sd_partition" pi-uefi-mount
sudo unzip RPi4_UEFI_Firmware_v1.53.zip -d pi-uefi-mount

ls -l pi-uefi-mount
test -f pi-uefi-mount/RPI_EFI.fd
test -f pi-uefi-mount/config.txt

sync
sudo umount pi-uefi-mount
```

Both file checks must succeed. Preserve the archive's filenames, directories, and `config.txt`; do not replace it with the Talos overlay's configuration. The ZIP is extracted onto a filesystem, not flashed as a disk image.

### First UEFI boot

1. With power off, leave USB storage disconnected and connect HDMI and a USB keyboard.
2. Insert the firmware card and power on.
3. Press **Esc** at the Raspberry Pi logo to enter UEFI setup. With no OS attached, a boot menu or shell is expected.
4. Under **Device Manager → Raspberry Pi Configuration → Advanced Configuration** (wording may vary), retain ACPI and initially retain the default 3 GB RAM limit.
5. Save settings, then cold boot and confirm that UEFI starts and settings persist.

After the first successful Talos boot, disable **Limit RAM to 3 GB**, reboot, and verify full memory availability plus working Ethernet and USB storage. The default limit addresses Pi DMA constraints; see [pftf's compatibility notes](https://github.com/pftf/RPi4#initial-notice).

The firmware card is ready once UEFI setup works. Keep it inserted. The next experiment is to boot a separate generic `metal-arm64.iso` USB installer, initially without the `rpi_generic` overlay. Exact image pins, scoped tooling, RAID selectors, and installation commands remain TODO. After installation, prefer the SSD boot entries over network boot entries in EDK2.

### Experiment record and acceptance checks

Record the repository revision, EEPROM and EDK2 versions/settings, Talos image/schematic, assigned disk identities, results, and remaining issues here. Do not mark these complete until tried.

- [ ] Firmware card reaches UEFI; settings survive a cold boot.
- [ ] Generic Talos ARM64 installer boots and sees Ethernet, both OS SSDs, and full RAM after removing the limit.
- [ ] Firmware card does not confuse Talos EFI/system-disk discovery.
- [ ] Installation onto MD RAID1 with metadata `1.0` completes without META deletion or copying firmware.
- [ ] Installed Talos cold boots with installation media removed.
- [ ] Cold boot succeeds with either OS SSD disconnected, tested separately after restoring mirror health between tests.
- [ ] Talos upgrade and subsequent cold boot work.
- [ ] Independent coordinator KMS unlock works, including a cold startup.

Results: **Not tried.**

If the firmware card fails, power off and recreate it from the pinned archive; recheck SD-first EEPROM boot. Preserve the previous boot media/settings for rollback. Reverting a Talos disk installation needs its own recovery procedure before destructive installation is attempted.

## Later platform and service milestones

- [ ] Validate Talos installation, boot, MD RAID1, and KMS encryption on the assigned OS disks; implement the pinned tooling and Trust bootstrap configuration.
- [ ] Document manual encrypted ZFS mirror preparation and deploy the planned platform services and OpenBao, including workstation/YubiKey unseal support.
- [ ] Verify cold startup, scheduled Raft snapshot backups, and the required restore paths; record results and update the recovery guide.

References: [Trust architecture](../clusters.md#trust), [hardware and disks](../inventory.md#trust), [repository layout](../layout.md#common-cluster-layout), [OpenBao unseal](../security/openbao-unseal.md), [backup and recovery](../backup-and-restore.md).
