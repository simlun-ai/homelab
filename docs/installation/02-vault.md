# 02 - Vault

**Draft experiment; not yet implemented or verified on hardware.**

Install the independent Vault cluster after the [main coordinator](01-main-coordinator.md) is ready. Firmware-card preparation can be tried separately while the coordinator/KMS work is pending.

## First installation experiment: Pi 4 UEFI

The first method to try is [pftf/RPi4](https://github.com/pftf/RPi4) firmware on a dedicated microSD card, booting a generic Talos ARM64 installer from USB and installing onto the assigned OS SSD mirror. This is a candidate installation method, not a settled design or a verified supported combination.

The SD card remains inserted for normal operation and is a boot dependency outside the SSD mirror. Keep all disk operations below confined to the firmware card; the [Vault data disks](../inventory.md#vault) are not installation targets.

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

## Remaining installation TODO

- [ ] Validate Talos installation, boot, MD RAID1, and KMS encryption on the assigned OS disks; implement the pinned tooling and Vault bootstrap configuration.
- [ ] Document manual encrypted ZFS mirror preparation and deploy the planned platform services and OpenBao, including workstation/YubiKey unseal support.
- [ ] Verify cold startup, scheduled Raft snapshot backups, and the required restore paths; record results and update the recovery guide.

References: [Vault architecture](../clusters.md#vault), [hardware and disks](../inventory.md#vault), [repository layout](../layout.md#common-cluster-layout), [OpenBao unseal](../security/openbao-unseal.md), [backup and recovery](../backup-and-restore.md).
