# Homelab Inventory

## Summary

- **Total disk capacity before mirroring:** 115,116 GB.
- **Total nominal usable capacity after mirroring:** 62,264 GB, excluding spare drives and cold-spare disks.
- **Total spare disk capacity:** 15,768 GB across 8 spare disks.
- **Total RAM:** 248 GB documented, plus unspecified RAM in three Raspberry Pi 3 shutdown coordinators and the old NAS computer.
- **Total computers:** 20, including two cold spares, three shutdown coordinators and the old NAS computer.
- **Total disks:** 76, including eight spare drives.

Raw disk capacity, RAM and equipment counts include cold spares and all drives listed under Spare Drives and Other disks. Usable capacity excludes the eight spare drives (15,768 GB) and the M920x cold spare's disks (512 GB after its OS mirror).

Capacity uses decimal units (1 TB = 1,000 GB). Each mirror contributes the capacity of its smallest member. Figures include OS disks and exclude filesystem overhead and any additional Piraeus replication. Unlisted boot media are not counted.

## Shared infrastructure nodes

- **UPS:** One Eaton 3S700 shared by the vault and backup clusters.
- **Shutdown coordinator:** 1 × Raspberry Pi 3, connected to the Eaton UPS via USB to coordinate safe shutdown of the cluster.

### vault (single-node)

- **Compute:** 1 × Raspberry Pi 4 with 8 GB RAM.
- **USB:** One official Raspberry Pi powered, four-port USB 3 hub.
- **Disks:** 3 × inexpensive, DRAM-less 128 GB Intenso USB SSDs.
- **OS drive:** 1 × 128 GB Intenso USB SSD.
- **Storage:** ZFS mirror (RAID 1) using the other 2 × 128 GB Intenso USB SSDs.
- **Power:** Official USB-C power adapters for the Pi and hub, supplied from 230 V mains.
- **Network:** 1 Gbit router connectivity, as for the pi cluster.
- **Boot configuration:** Latest EEPROM firmware, with USB boot given priority.

### backup (single-node)

- **Compute:** Lenovo ThinkCentre M93p Tiny.
- **RAM:** 8 GB.
- **OS drive:** Intel 180 GB SSD.
- **Storage:** ZFS mirror (RAID 1), consisting of two 8 TB Samsung USB HDDs, each with a 3.5-inch form factor.

## pi cluster

- **Compute:** 5 × Raspberry Pi 4, each with 8 GB RAM. One Raspberry Pi 4 8 GB RAM cold spare as well.
- **Shutdown coordinator:** 1 × Raspberry Pi 3, connected to the Eaton UPS via USB to coordinate safe shutdown of the cluster.
- **USB:** One official Raspberry Pi powered, four-port USB 3 hub per Pi.
- **Disks:** 15 × 128 GB SATA SSDs in total, three per Raspberry Pi 4; models and layout listed below.
- **Power:** Official USB-C power adapters for both the Pis and hubs, supplied from 230 V mains.
- **Network:** One Netgear 1 Gbit router connecting all five Pis.
- **UPS:** Everything powered through an Eaton 3S850.
- **Boot configuration:** All five Raspberry Pi 4 nodes running the latest EEPROM firmware, with USB boot given priority.

### SSD inventory and layout

15 × cheap DRAM-less 128 GB SATA SSDs available for the cluster, connected through SATA-to-USB 3 adapters:

| Model | Quantity | Capacity per SSD / combined sum |
| --- | --- | --- |
| Patriot P220 | 5 | 128 GB |
| Silicon Power A5X | 5 | 128 GB |
| Intenso TOP | 2 | 128 GB |
| Fanxiang S101 | 3 | 128 GB |
| **Sum** | **15** | **1,920 GB** |

Each of the five Raspberry Pi 4 nodes gets three SSDs:

- **OS:** Two SSDs per Pi in MD RAID1 (10 SSDs across the cluster).
- **Piraeus data plane:** One SSD per Pi (5 SSDs across the cluster).

### SSD allocation

Planned allocation; Pi 1–3 are control-plane nodes and Pi 4–5 are workers. All SSDs are 128 GB. OS disk 1 and OS disk 2 form each node's MD RAID1; the data SSD joins the Piraeus data plane.

| Node | Role | OS disk 1 | OS disk 2 | Piraeus data SSD |
| --- | --- | --- | --- | --- |
| Pi 1 | Control plane | Silicon Power A5X | Fanxiang S101 | Patriot P220 |
| Pi 2 | Control plane | Patriot P220 | Fanxiang S101 | Silicon Power A5X |
| Pi 3 | Control plane | Patriot P220 | Silicon Power A5X | Fanxiang S101 |
| Pi 4 | Worker | Silicon Power A5X | Intenso TOP | Patriot P220 |
| Pi 5 | Worker | Patriot P220 | Silicon Power A5X | Intenso TOP |

The three control-plane data SSDs have different brands, and the two worker data SSDs have different brands. Each Pi's OS pair also has different brands; this allocation gives every Pi three different SSD brands in total. All 15 SSDs are allocated, with none left over.

## metal cluster

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
- **SATA1:** PNY 120 GB SSD (OS MD RAID1).
- **SATA2:** Intenso TOP 128 GB SSD (OS MD RAID1).
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
- **SATA1:** PNY 120 GB SSD (OS MD RAID1).
- **SATA2:** Intenso TOP 128 GB SSD (OS MD RAID1).
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
- **SATA1:** PNY 120 GB SSD (OS MD RAID1).
- **SATA2:** OCZ Vertex 4 128 GB SSD (OS MD RAID1).
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
- **SATA1:** Silicon Power A5X 128 GB SSD (OS MD RAID1).
- **SATA2:** Patriot P220 128 GB SSD (OS MD RAID1).
- **ZFS mirror pool `nvr`:**
  - **SATA3:** 1500 GB SATA HDD.
  - **SATA4:** 1500 GB SATA HDD.
- **ZFS mirror pool `piraeus`:**
  - **NVMe1:** Fanxiang S500Pro 256 GB SSD.
  - **NVMe2:** Patriot P320 256 GB SSD.
- **1 Gbit MAC address:** TBD.
- **2.5 Gbit MAC address:** TBD.

### UPS and shutdown coordination

Three Eaton UPS units protect the metal cluster:

| UPS | Model | Protected equipment |
| --- | --- | --- |
| 1 | Eaton 3S850 | Three control-plane nodes, the Pi3 coordinator and all network switches |
| 2 | Eaton 3S850 | worker1 and worker2 |
| 3 | Eaton 3S700 | worker3 and worker4 |

**Shutdown coordinator:** 1 × Raspberry Pi 3 for the whole cluster.

## Spare Drives

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
