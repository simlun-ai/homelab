# Homelab Inventory

## Shared infrastructure

- **UPS:** One Eaton 3S USV 3S850D shared by the vault and backup clusters.

### vault

- **Compute:** 1 × Raspberry Pi 4 with 8 GB RAM.
- **Shutdown coordinator:** The Raspberry Pi 4 itself, connected to the Eaton UPS via USB to coordinate its own safe shutdown.
- **USB:** One official Raspberry Pi powered, four-port USB 3 hub.
- **Disks:** 3 × inexpensive, DRAM-less 128 GB Intenso USB SSDs.
- **OS drive:** 1 × 128 GB Intenso USB SSD.
- **Storage:** ZFS mirror (RAID 1) using the other 2 × 128 GB Intenso USB SSDs.
- **Power:** Official USB-C power adapters for the Pi and hub, supplied from 230 V mains.
- **Network:** 1 Gbit router connectivity, as for the pi cluster.
- **Boot configuration:** Latest EEPROM firmware, with USB boot given priority.

### backup

- **Compute:** Lenovo ThinkCentre M93p Tiny.
- **RAM:** 8 GB.
- **OS drive:** Intel 180 GB SSD.
- **Storage:** ZFS mirror (RAID 1), consisting of two 8 TB Samsung USB HDDs, each with a 3.5-inch form factor.

## pi cluster

- **Compute:** 5 × Raspberry Pi 4, each with 8 GB RAM.
- **Shutdown coordinator:** 1 × Raspberry Pi 3, to be connected to the Eaton UPS via USB to coordinate safe shutdown of the cluster.
- **USB:** One official Raspberry Pi powered, four-port USB 3 hub per Pi.
- **Storage:** 3 × inexpensive, DRAM-less 128 GB SATA SSDs, connected through decent SATA-to-USB 3 adapters.
- **Power:** Official USB-C power adapters for both the Pis and hubs, supplied from 230 V mains.
- **Network:** One 1 Gbit router connecting all five Pis.
- **UPS:** Everything powered through an Eaton 3S USV 3S850D.
- **Boot configuration:** All five Raspberry Pi 4 nodes running the latest EEPROM firmware, with USB boot given priority.

## metal cluster

### Control plane

Three Lenovo ThinkCentre M920x nodes and one Lenovo ThinkCentre M920x cold spare.

Each machine has:

- **RAM:** 8 GB.
- **SATA:** 1 × 256 GB SSD.
- **NVMe:** 2 × 256 GB SSDs.
- **OS:** MD RAID1 across the two NVMe SSDs.
- **Storage:** Piraeus on ZFS for the SATA SSD.

| Inventory entry | Role | 1 Gbit MAC address | 2.5 Gbit MAC address |
| --- | --- | --- | --- |
| M920x 1 | Control plane | TBD | TBD |
| M920x 2 | Control plane | TBD | TBD |
| M920x 3 | Control plane | TBD | TBD |
| M920x cold spare | Cold spare | TBD | TBD |

### Workers

All workers use MD RAID1 across SATA1 and SATA2 for the OS.

#### worker1

- **Compute:** Lenovo ThinkCentre M900, Intel Core i7-6700.
- **RAM:** 40 GB.
- **SATA1:** PNY 120 GB SSD.
- **SATA2:** OCZ Vertex 4 128 GB SSD.
- **NVMe1:** Samsung SSD 990 PRO 4 TB.
- **NVMe2:** Samsung PM951 256 GB (mzvlv256hchp-000L1).
- **1 Gbit MAC address:** `4C:CC:6A:C3:C7:15`.
- **2.5 Gbit MAC address:** `1C:86:0B:2B:38:42`.

#### worker2

- **Compute:** Lenovo ThinkCentre M900, Intel Core i5-6400.
- **RAM:** 40 GB.
- **SATA1:** PNY 120 GB SSD.
- **SATA2:** Intenso TOP 128 GB SSD.
- **NVMe1:** Transcend PCIe SSD 110S 256 GB (TS256GMTE110S).
- **NVMe2:** Fanxiang 256 GB SSD.
- **1 Gbit MAC address:** `1c:66:6d:98:ea:02`.
- **2.5 Gbit MAC address:** `1c:86:0b:2b:39:cb`.

#### worker3

- **Compute:** Lenovo ThinkCentre M900, Intel Core i5-6400.
- **RAM:** 40 GB.
- **SATA1:** PNY 120 GB SSD.
- **SATA2:** Intenso TOP 128 GB SSD.
- **NVMe1:** Transcend PCIe SSD 110S 256 GB (TS256GMTE110S).
- **NVMe2:** Patriot P320 256 GB SSD.
- **1 Gbit MAC address:** `1c:66:6d:98:d6:6e`.
- **2.5 Gbit MAC address:** `1c:86:0b:2b:39:0f`.

#### worker4

- **Compute:** Desktop chassis with an MSI H77MA-G43 motherboard.
- **RAM:** 32 GB.
- **SATA1:** Silicon Power A5X 128 GB SSD.
- **SATA2:** Patriot P220 128 GB SSD.
- **NVMe1:** Fanxiang S500Pro 256 GB SSD.
- **NVMe2:** Patriot P320 256 GB SSD.
- **1 Gbit MAC address:** TBD.
- **2.5 Gbit MAC address:** TBD.
