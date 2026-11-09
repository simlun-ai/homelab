# Homelab Inventory

## Summary

- **Total disk capacity before mirroring:** 115,244 GB.
- **Total nominal usable capacity after mirroring:** 62,264 GB, excluding spare drives and cold-spare disks.
- **Total spare disk capacity:** 15,768 GB across 8 spare disks.
- **Total RAM:** 251 GB documented, including the three 1 GB shutdown coordinators, plus unspecified RAM in the old NAS computer.
- **Total computers:** 20, including two cold spares, three shutdown coordinators and the old NAS computer.
- **Total disks:** 77, including eight spare drives.

Raw disk capacity, RAM and equipment counts include cold spares and all drives listed under Spare Drives and Other disks. Usable capacity excludes the eight spare drives (15,768 GB) and the M920x cold spare's disks (512 GB after its OS mirror).

Capacity uses decimal units (1 TB = 1,000 GB). Each mirror contributes the capacity of its smallest member. Figures include OS disks and exclude filesystem overhead and any additional Piraeus replication. Unlisted boot media are not counted.

See [clusters.md](clusters.md) for architecture, [network.md](network.md) for VLANs and addressing, [security.md](security/security.md#disk-encryption-and-opentofu) for encryption, and [layout.md](layout.md) for provisioning and power-return policy.

All UPS shutdown coordinators will use Raspberry Pi 3 Model B computers with 1 GB RAM. Each will boot Raspberry Pi OS Lite (64-bit) from a microSD card; card models/capacities are TBD and remain excluded from disk totals as unlisted boot media. Each will use a suitably rated 230 V AC to 5 V DC power adapter connected to a battery-backed outlet of the UPS it monitors.

Per-device power-return support, settings, and verification remain TBD, including Pis, coordinators, and UPS outlets.

## Trust

- **Compute:** 1 × Raspberry Pi 4 Model B with 8 GB RAM (nominal inventory capacity). Live discovery reported SMBIOS version `D03115` and serial `1000000089261F6E` on 2026-11-09.
- **Hardware UUID (observed):** `00d03115-0000-0000-1000-000089261f6e`. Unchanged across the recorded cold boot after disabling the UEFI RAM cap on 2026-11-09. Stability across other firmware changes/reinstall remains unverified; not yet an operational KMS registration.
- **Live memory verification:** `talosctl memory` TOTAL increased from `2848` to `7748` (about 7.6 GiB) after disabling the UEFI 3 GB cap and cold booting on 2026-11-09; AVAILABLE was `7203`. The same UUID and working Ethernet were retained. Nominal inventory RAM remains 8 GB; aggregate RAM totals are unchanged.
- **USB:** One official Raspberry Pi powered, four-port USB 3 hub.
- **Disks (provisional allocation):** Four 128 GB SATA SSD candidates inspected individually on the workstation and detected together on the Pi. See [candidate disk inventory](#candidate-disk-inventory) for the observed identities and signatures. Final disk selection and pair assignments are pending.
- **OS drives:** Planned MD RAID1 using two disks (128 GB nominal usable); exact disk assignment TBD.
- **Storage:** Planned ZFS mirror (RAID 1) using the other two disks (128 GB nominal usable); exact disk assignment TBD.
- **Capacity accounting:** Summary totals use this provisional allocation: 512 GB raw and 256 GB nominal usable across the two mirrors. Final allocation will be confirmed after reviewing the candidate inventory.
- **Power:** Official USB-C power adapters for the Pi and hub, supplied from 230 V mains.
- **Network:** 1 Gbit Ethernet on `k8s-aux` (VLAN 10); planned static `10.10.0.10` and node hostname `trust-cp1.k8s-aux.lundmark.internal`. Live Talos discovery uses DHCP. Observed physical interface `enabcm6e4ei0`, alternative name `enxd83add37d639`, permanent MAC `d8:3a:dd:37:d6:39`, driver `bcmgenet`, link up at 1000 Mbit/s/full duplex (2026-11-09). The provisional `eth0` patch must be corrected before apply; see the [experiment record](installation/02-trust.md#experiment-record-and-acceptance-checks).
- **Boot configuration:** Operator completed SD-first EEPROM configuration and reached pftf/EDK2 UEFI setup from the dedicated firmware microSD card on 2026-11-08. UEFI Firmware v1.53 was confirmed on 2026-11-09, with setup reached again after a full power cycle and no settings changes. On the same date the operator manually selected the USB installer in UEFI Boot Manager and reached Talos maintenance mode. The UEFI 3 GB RAM cap was then disabled and the change remained effective after a full cold boot, with memory and Ethernet verified. Exact EEPROM version and BOOT_ORDER, other modified settings and automatic USB selection remain unverified. See the [UEFI experiment results](installation/02-trust.md#experiment-record-and-acceptance-checks). See the [live Talos disk inventory](#live-talos-disk-inventory) for the observed boot media. Boot media are excluded from disk totals.

### Candidate disk inventory

Read-only workstation inspection on 2026-11-09. Each candidate was presented
as `/dev/sda` and displayed `119.2G` in `lsblk`. No partitions or mountpoints
were listed. The ATA links below were observed on `simlun-x1`.

| Candidate | Reported model | ATA serial | Workstation device link | Signatures reported by `wipefs --no-act` |
| --- | --- | --- | --- | --- |
| 1 | Intenso SSD Sata III | `2025032901388` | `/dev/disk/by-id/ata-Intenso_SSD_Sata_III_2025032901388` | DOS/MBR signature at `0x1fe` |
| 2 | SPCC Solid State Disk | `WWDD241210062007013` | `/dev/disk/by-id/ata-SPCC_Solid_State_Disk_WWDD241210062007013` | None reported |
| 3 | Fanxiang S101 128GB | `26060780625001902` | `/dev/disk/by-id/ata-Fanxiang_S101_128GB_26060780625001902` | None reported |
| 4 | Patriot P220 128GB | `P220HHBB251201003962` | `/dev/disk/by-id/ata-Patriot_P220_128GB_P220HHBB251201003962` | None reported |

All four observations used the same workstation USB path
(`pci-0000:00:14.0-usb-0:2:1.0-scsi-0:0:0:0`). The operator reports four
identical USB-to-SATA adapters. The sampled adapter enumerated on `simlun-x1`
as ASMedia ASM1153 SATA 3Gb/s bridge, USB ID `174c:1153`. The adapter retail make and model remain unrecorded.

#### Live Talos disk inventory

Read-only Talos maintenance-mode discovery on `10.10.0.246` on 2026-11-09.
All four candidates were detected together through the powered USB hub.
Each exposed the same ATA device link as on the workstation and reported
128,035,676,160 bytes with a 512-byte sector size and 512-byte I/O size.

| Candidate | Talos device at discovery | USB device link reported by Talos |
| --- | --- | --- |
| 1 (Intenso) | `/dev/sda` | `/dev/disk/by-id/usb-Intenso_SSD_Sata_III_26A1EE830094-0:0` |
| 2 (SPCC) | `/dev/sde` | `/dev/disk/by-id/usb-SPCC_Sol_id_State_Disk_26A1EE833C38-0:0` |
| 3 (Fanxiang) | `/dev/sdb` | `/dev/disk/by-id/usb-Fanxiang_S101_128GB_26A1EE833E35-0:0` |
| 4 (Patriot) | `/dev/sdd` | `/dev/disk/by-id/usb-Patriot_P220_128GB_26A1EE833C2F-0:0` |

All four reported WWID `naa.5000000000000001`, so the WWID cannot identify
an individual SSD. The `/dev/sd*` names are a snapshot of this boot. Use the
`/dev/disk/by-id/ata-*` links listed above as the physical SSD identifiers
for Trust. They include the SSD's ATA serial and matched across the
workstation and Pi. The `usb-*` links describe the USB side of each
connection. ATA link stability across reboots and final mirror assignments
are pending.

| Boot medium | Talos device at discovery | Reported capacity (bytes) | Device link |
| --- | --- | ---: | --- |
| UEFI microSD | `/dev/mmcblk1` | 15,931,539,456 | `/dev/disk/by-id/mmc-SC16G_0x19739311` |
| USB Talos installer | `/dev/sdc` | 31,037,849,600 | `/dev/disk/by-id/usb-Generic_Flash_Disk_22040353520091-0:0` |

## Backup

- **Compute:** Lenovo ThinkCentre M93p Tiny.
- **RAM:** 8 GB.
- **OS drive:** Intel 180 GB SSD.
- **Storage:** ZFS mirror (RAID 1), consisting of two 8 TB Samsung USB HDDs, each with a 3.5-inch form factor.
- **Network:** `k8s-aux` (VLAN 10), static `10.10.0.15`.

## Shared infrastructure

Shared exclusively by the **Trust and Backup clusters**:

- **UPS:** 1 × Eaton 3S700 supplying power to both clusters.
- **Shutdown coordinator:** `ups-aux`, 1 × Raspberry Pi 3 Model B with 1 GB RAM and static `10.10.0.5` on `k8s-aux` (VLAN 10). **Wired Ethernet MAC address:** `b8:27:eb:58:e9:8f`. It connects to the UPS via USB for monitoring and safe shutdown of both clusters and is the planned host for [Trust's bootstrap KMS](security/security.md#trust-bootstrap-kms).

## Pi

- **Compute:** 5 active Raspberry Pi 4 nodes and 1 cold spare, each with 8 GB RAM.
- **Shutdown coordinator:** `ups-pi`, 1 × Raspberry Pi 3 Model B with 1 GB RAM, connected to the Eaton UPS via USB to coordinate safe shutdown of the cluster.
- **USB:** One official Raspberry Pi powered, four-port USB 3 hub per Pi.
- **Disks:** SATA SSDs through SATA-to-USB 3 adapters; [models and allocation](#ssd-inventory-and-layout) below.
- **Power:** Official USB-C power adapters for both the Pis and hubs, supplied from 230 V mains.
- **Network:** One Netgear 1 Gbit switch connects all five Pis on `k8s-pi` (VLAN 11).
- **UPS:** Everything powered through an Eaton 3S850.
- **Boot configuration:** All five Raspberry Pi 4 nodes running the latest EEPROM firmware, with USB boot given priority.

### SSD inventory and layout

All SSDs are inexpensive, DRAM-less, and 128 GB:

| Model | Quantity | Capacity per SSD / combined sum |
| --- | --- | --- |
| Patriot P220 | 5 | 128 GB |
| Silicon Power A5X | 5 | 128 GB |
| Intenso TOP | 2 | 128 GB |
| Fanxiang S101 | 3 | 128 GB |
| **Sum** | **15** | **1,920 GB** |

### SSD allocation

Planned allocation: each node has an MD RAID1 OS pair and one Piraeus data SSD (10 OS + 5 data SSDs).

Each of the five data SSDs forms a single-disk ZFS pool named `piraeus` to leverage ZFS checksumming. These pools follow the [Workload and Piraeus placement strategy](clusters.md#workload-and-piraeus-placement).

| Node | Role | OS disk 1 | OS disk 2 | Piraeus data SSD |
| --- | --- | --- | --- | --- |
| Pi 1 | Control plane | Silicon Power A5X | Fanxiang S101 | Patriot P220 |
| Pi 2 | Control plane | Patriot P220 | Fanxiang S101 | Silicon Power A5X |
| Pi 3 | Control plane | Patriot P220 | Silicon Power A5X | Fanxiang S101 |
| Pi 4 | Worker | Silicon Power A5X | Intenso TOP | Patriot P220 |
| Pi 5 | Worker | Patriot P220 | Silicon Power A5X | Intenso TOP |

Each node has three different SSD brands; data brands also differ within each role group. All 15 SSDs are allocated.

## Metal

### Control plane

Three Lenovo ThinkCentre M920x nodes and one Lenovo ThinkCentre M920x cold spare.

Each machine has:

- **RAM:** 8 GB.
- **SATA:** 1 × 256 GB SSD.
- **NVMe:** 2 × 256 GB SSDs.
- **OS:** MD RAID1 across the two NVMe SSDs.
- **Storage:** The SATA SSD is a single disk ZFS pool `piraeus` for the cluster-wide Piraeus data plane.

| Inventory entry | Role | 1 Gbit MAC address | 2.5 Gbit MAC address |
| --- | --- | --- | --- |
| M920x 1 | Control plane | TBD | TBD |
| M920x 2 | Control plane | TBD | TBD |
| M920x 3 | Control plane | TBD | TBD |
| M920x cold spare | Cold spare | TBD | TBD |

### Workers

All workers use MD RAID1 across SATA1 and SATA2 for the OS.

#### worker1

- **Compute:** Lenovo ThinkCentre M900, Intel Core i5-6400.
- **RAM:** 40 GB.
- **SATA1:** PNY 120 GB SSD.
- **SATA2:** Intenso TOP 128 GB SSD.
- **ZFS mirror pool `piraeus`:**
  - **NVMe1:** Transcend PCIe SSD 110S 256 GB (TS256GMTE110S).
  - **NVMe2:** Patriot P320 256 GB SSD.
- **ZFS mirror pool `immich`:** 2 × Samsung T7 1 TB USB SSDs, connected via USB 3.
- **ZFS mirror pool `photos`:** 2 × Seagate Portable Drive 2.5-inch 4 TB USB HDDs, connected via USB 3.
- **ZFS mirror pool `media`:** 2 × 3 TB SATA HDDs, each connected through a SATA–USB 3 adapter.
- **1 Gbit MAC address:** `1c:66:6d:98:d6:6e`.
- **2.5 Gbit MAC address:** `1c:86:0b:2b:39:0f`.

#### worker2

- **Compute:** Lenovo ThinkCentre M900, Intel Core i5-6400.
- **RAM:** 40 GB.
- **SATA1:** PNY 120 GB SSD.
- **SATA2:** Intenso TOP 128 GB SSD.
- **ZFS mirror pool `piraeus`:**
  - **NVMe1:** Transcend PCIe SSD 110S 256 GB (TS256GMTE110S).
  - **NVMe2:** Fanxiang 256 GB SSD.
- **ZFS mirror pool `dump`:** 2 × 2 TB SATA HDDs, each connected through a SATA–USB 3 adapter.
- **ZFS mirror pool `nas`:** 2 × 4 TB SATA HDDs, each connected through a SATA–USB 3 adapter.
- **1 Gbit MAC address:** `1c:66:6d:98:ea:02`.
- **2.5 Gbit MAC address:** `1c:86:0b:2b:39:cb`.

#### worker3

- **Compute:** Lenovo ThinkCentre M900, Intel Core i7-6700.
- **RAM:** 40 GB.
- **SATA1:** PNY 120 GB SSD.
- **SATA2:** OCZ Vertex 4 128 GB SSD.
- **NVMe1:** Samsung SSD 990 PRO 4 TB, with an XFS filesystem labeled `ethereum`.
- **ZFS single-disk pool `piraeus`:**
  - **NVMe2:** Samsung PM951 256 GB (mzvlv256hchp-000L1).
- **ZFS mirror pool `bitcoin`:** 2 × Samsung 870 EVO 2 TB SATA SSDs, each connected through a USB 3–SATA adapter.
- **1 Gbit MAC address:** `4C:CC:6A:C3:C7:15`.
- **2.5 Gbit MAC address:** `1C:86:0B:2B:38:42`.

#### worker4

- **Compute:** Desktop chassis with an MSI H77MA-G43 motherboard.
- **RAM:** 32 GB.
- **Accelerator:** Coral USB Accelerator with an Edge TPU coprocessor.
- **SATA1:** Silicon Power A5X 128 GB SSD.
- **SATA2:** Patriot P220 128 GB SSD.
- **ZFS mirror pool `nvr`:**
  - **SATA3:** 1500 GB SATA HDD.
  - **SATA4:** 1500 GB SATA HDD.
- **ZFS mirror pool `piraeus`:**
  - **NVMe1:** Fanxiang S500Pro 256 GB SSD.
  - **NVMe2:** Patriot P320 256 GB SSD.
- **1 Gbit MAC address:** TBD.
- **2.5 Gbit MAC address:** TBD.

### Dedicated storage network

- **Available switches:** 2 × five-port 2.5 Gbit/s Ethernet switches; models TBD.
- **Use and topology:** See [cluster networking](clusters.md#dedicated-storage-network).

### UPS and shutdown coordination

Three Eaton UPS units protect Metal:

| UPS | Model | Protected equipment |
| --- | --- | --- |
| 1 | Eaton 3S850 | Three control-plane nodes, the shutdown coordinator and all network switches |
| 2 | Eaton 3S850 | worker1 and worker2 |
| 3 | Eaton 3S700 | worker3 and worker4 |

**Shutdown coordinator:** `ups-metal`, 1 × Raspberry Pi 3 Model B with 1 GB RAM for the whole cluster, powered from UPS 1. Monitoring connections to the three UPS units remain TBD.

## Security keys

Four YubiKeys available; use cases and proposed lookups belong in [yubikey.md](security/yubikey.md), and configuration/custody policy in [security.md](security/security.md#core-secret-foundation).

| Label | Model | Firmware | Serial | Enabled interfaces |
| --- | --- | --- | --- | --- |
| key0 | YubiKey 5 NFC | 5.2.4 | 10649811 | OTP + FIDO + CCID |
| key1 | YubiKey 5 NFC | 5.2.4 | 10649813 | OTP + FIDO + CCID |
| key2 | YubiKey Standard | 2.4.1 | 1903813 | OTP |
| key3 | YubiKey Standard | 2.2.3 | 1020513 | OTP |

**Total: 4 tokens.** All four were programmed in OTP slot 2 with the same
`golden-1` key and passed physical touch/HMAC and cross-token/software checks
on 2026-11-04. Slot 1 was preserved. Detailed acceptance results belong in
[step 00](installation/00-yubikey-setup.md#5-record-results-replicate-and-finish).

## Spare drives

- Samsung SSD 870 EVO 2 TB.
- Samsung USB SSD T7 1 TB.
- Patriot P220 128 GB SATA SSD.
- Silicon Power A5X 256 GB SATA SSD.
- Fanxiang 256 GB NVMe SSD.
- Intenso 128 GB Portable SSD Premium USB.
- Seagate Expansion 3.5-inch 8 TB USB HDD.
- Seagate Portable Drive 2.5-inch 4 TB USB HDD.

## Other disks

- **Restore disk:** 1 × Seagate 3.5" HDD, 20 TB, connected via USB (20,000 GB usable).
- **Old NAS storage:** 4 × 4 TB 2.5" USB HDDs in ZFS RAID10 (two mirrored vdevs): 16,000 GB raw, 8,000 GB nominal usable.
