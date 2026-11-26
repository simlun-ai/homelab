# 03 - Backup

The first milestone is a cold boot of `backup-cp1` with encrypted `STATE` and
`EPHEMERAL` unlocked through [Trust's KMS adapter](trust-talos-kms.md).
Finish the remaining Trust work after this check. Backup Kubernetes bootstrap
and the data pool and workloads are later steps.

## Review and validate the config

The [public patch](../../clusters/backup/talos/backup-cp1.yaml) uses the two
exact OS disk links in the [Backup inventory](../inventory.md#backup) as RAID1
members and targets the named array for installation. Review the live Talos
disk identities against the patch before installing. The two Seagate drives
are reserved for the manually managed data mirror.

From the operator workstation, install the checksum-verified Backup
`talosctl` and validate the complete configuration shape offline:

```sh
make -C clusters/backup tools
make -C clusters/backup validate
```

Validation uses disposable credentials in a pipe and checks the public patch
with its pinned installer reference. The planned single-node Kubernetes API
endpoint is `https://10.10.0.15:6443`.

## Prepare the boot assets

Use the public [Image Factory schematic](../../clusters/backup/talos/backup-cp1.schematic.yaml)
for both the amd64 ISO and the installer. It configures static networking
before Talos opens `STATE`. Early DNS uses the gateway, and Talos defaults to
`time.cloudflare.com` for time synchronization.

When the schematic changes, regenerate its ID using the same Make workflow as
Trust. This submits the public YAML to Image Factory and updates the adjacent
`.id` file. Refresh the installer manifest pin and ISO checksum for the new ID.

```sh
make -C clusters/backup schematic-id SCHEMATIC=talos/backup-cp1.schematic.yaml
```

On the Linux workstation, from the repository root, download and verify the
ISO before writing it to the installer USB:

```sh
(
  set -eu
  out=clusters/backup/boot
  schematic=$(cat clusters/backup/talos/backup-cp1.schematic.id)
  mkdir -p "$out"
  curl --fail --location --show-error \
    --output "$out/metal-amd64.iso" \
    "https://factory.talos.dev/image/$schematic/v1.14.5/metal-amd64.iso"
  printf '%s  %s\n' 'd49b3e952cc5c5fa204b3acfe7f40afcaa75529ecb3081255c2eb9bf5cf2196b' "$out/metal-amd64.iso" |
    sha256sum --check -
)
```

The checksum was computed from the downloaded Factory ISO. The boot arguments
from the Factory and the embedded `ip=` argument in the pinned amd64 installer
both matched the schematic. Talos pulls that installer during installation.
On subsequent boots, Talos loads the installed boot image from disk.

## First encrypted boot

Before applying a configuration, create and back up a separate wrapped Backup
Talos identity and assemble and validate the real configuration in memory.
Use the custom ISO to start in maintenance mode, and confirm the target UUID
and both OS disk identities. Installation writes to the selected OS disks.

After installation, remove the USB stick and cold-boot from the mirror.
Verify static addressing, DNS and time, then verify that `STATE` and
`EPHEMERAL` unlock through the Trust KMS endpoint. Record the outcome here.

| Check | Status |
| --- | --- |
| Hardware discovery | [Verified in maintenance mode](../inventory.md#backup). |
| Trust KMS deployment | [Rolled out with workload state published](02-trust.md#next-milestone-first-backup-kms-boot). |
| Public Talos config | Offline rehearsal only. |
| Factory ISO and installer | ISO downloaded and checksum recorded. Installer pinned by amd64 manifest digest. |
| Production config and first cold boot | Pending. |
