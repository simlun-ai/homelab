# Homelab Inventory

## Shared infrastructure

- **UPS:** One Eaton 3S USV 3S850D shared by the vault and backup clusters.

### vault

- **Compute:** 1 × Raspberry Pi 4 with 8 GB RAM.
- **Shutdown coordinator:** The Raspberry Pi 4 itself, connected to the Eaton UPS via USB to coordinate its own safe shutdown.
- **USB:** One official Raspberry Pi powered, four-port USB 3 hub.
- **Storage:** 3 × inexpensive, DRAM-less 128 GB Intenso USB SSDs.
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

Inventory details to be added.
