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

When the schematic or pinned Talos release changes, use the same Make workflow
as Trust. This submits the public YAML to Image Factory, selects the amd64
manifest, and verifies it by SHA-256. Commit the regenerated `.id` and
`.amd64.image` files and refresh the ISO URL version and checksum below.

```sh
make -C clusters/backup installer-image SCHEMATIC=talos/backup-cp1.schematic.yaml
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

## Enroll and validate the Backup identity

On the workstation, initialize and update the private `secrets/wrapped`
submodule, then prepare the pinned HSM environment:

```sh
make -C support/hsm tools
make -C clusters/backup secrets-init
```

Touch the YubiKey when prompted. The target generates the Backup Talos
authority once and wraps it as `secrets/wrapped/backup-talos-bootstrap.json`
under `homelab/v1/backup/talos/bootstrap/r1`. If the record already exists,
continue with validation using that record. Publish the ciphertext in the
private submodule and commit its updated pointer before installing.

```sh
make -C clusters/backup install-config-validate
```

This recovers the same identity with the YubiKey and validates the complete
machine config offline. It keeps the recovered identity and the assembled
config in memory. Expect native strict metal validation to pass.

## First encrypted boot

1. Boot the verified Factory ISO from USB. Wait for maintenance mode at
   `10.10.0.15` and keep the console visible.
2. From the workstation, run `make -C clusters/backup install-config-apply`
   only when ready to write the two assigned OS disks. The helper recovers
   and validates the same in-memory config, checks the maintenance UUID
   against the KMS registration, and verifies both RAID members by their
   exact disk links before sending the config.
3. Watch the console for installation completion. If the apply is interrupted,
   check the console before retrying. Remove the USB stick and cold-boot from
   the installed mirror once installation completes.
4. Check the console for static addressing, DNS, time sync, and KMS unlock.
   From the workstation, run `make -C clusters/backup install-status` with the
   YubiKey. It issues a fresh in-memory Talos client and verifies that
   `STATE` and `EPHEMERAL` are both `ready` with LUKS2 reported.
   Record the outcome here and in the Trust roadmap.

| Check | Status |
| --- | --- |
| Hardware discovery | [Verified in maintenance mode](../inventory.md#backup). |
| Trust KMS deployment | [Rolled out with workload state published](02-trust.md#next-milestone-first-backup-kms-boot). |
| Public Talos config | Offline rehearsal only. |
| Factory ISO and installer | ISO downloaded and checksum recorded. Installer pinned by amd64 manifest digest. |
| Production config and first cold boot | Pending. |
