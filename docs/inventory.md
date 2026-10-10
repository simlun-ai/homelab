# Homelab Inventory

## pi

- **Compute:** 5 × Raspberry Pi 4, each with 8 GB RAM.
- **Shutdown coordinator:** 1 × Raspberry Pi 3, to be connected to the Eaton UPS via USB to coordinate safe shutdown of the cluster.
- **USB:** One official Raspberry Pi powered, four-port USB 3 hub per Pi.
- **Storage:** 3 × inexpensive, DRAM-less 128 GB SATA SSDs, connected through decent SATA-to-USB 3 adapters.
- **Power:** Official USB-C power adapters for both the Pis and hubs, supplied from 230 V mains.
- **Network:** One 1 Gbit router connecting all five Pis.
- **UPS:** Everything powered through an Eaton 3S USV 3S850D.
- **Boot configuration:** All five Raspberry Pi 4 nodes running the latest EEPROM firmware, with USB boot given priority.

## vault

- **Compute:** 1 × Raspberry Pi 4 with 8 GB RAM.
- **Shutdown coordinator:** No Raspberry Pi 3.
- **USB:** One official Raspberry Pi powered, four-port USB 3 hub.
- **Storage:** 3 × inexpensive, DRAM-less 128 GB SATA SSDs, connected through decent SATA-to-USB 3 adapters.
- **Power:** Official USB-C power adapters for the Pi and hub, supplied from 230 V mains.
- **Network:** 1 Gbit router connectivity, as for the pi cluster.
- **UPS:** Eaton 3S USV 3S850D power protection, as for the pi cluster.
- **Boot configuration:** Latest EEPROM firmware, with USB boot given priority.

## backup

Inventory details to be added.

## metal

Inventory details to be added.
