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

Validation uses disposable credentials in a pipe and a reserved `.invalid`
installer reference. The planned single-node Kubernetes API endpoint is
`https://10.10.0.15:6443`.

## Prepare the boot assets

The installed kernel needs the [early network argument](../../clusters/backup/talos/early-network.args)
before it can unlock `STATE`. Build both the amd64 ISO and installer locally
with the same argument. Early DNS uses the gateway, and Talos defaults to
`time.cloudflare.com` for time synchronization. Verify DNS and time during the
first Backup boot.

On the Linux Docker workstation, from the repository root:

```sh
(
  set -eu
  release=$(awk '/^talos:$/ {getline; print $2}' clusters/backup/versions.yaml)
  kernel_arg=$(cat clusters/backup/talos/early-network.args)
  out="$PWD/clusters/backup/boot"
  mkdir -p "$out"

  for asset in iso installer; do
    docker run --rm --platform linux/amd64 --user "$(id -u):$(id -g)" \
      --volume "$out:/out" "ghcr.io/siderolabs/imager:$release" "$asset" \
      --arch amd64 --base-installer-image "ghcr.io/siderolabs/installer-base:$release" \
      --extra-kernel-arg "$kernel_arg"
  done
)
```

Expect `metal-amd64.iso` and `installer-amd64.tar` in the boot directory.
Publish the installer to Trust's Zot using the
[publisher credentials workflow](trust-zot.md#publish-the-first-image).
Record the amd64 manifest digest. Use the digest-pinned reference with
`talosctl gen config --install-image` when assembling the real configuration.
Check the exact `ip=` argument in the installer's amd64 UKI using the
[Trust verification procedure](02-trust.md#verify-the-installer-boot-arguments).
Keep that verification offline.

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
| Custom image, production config and first cold boot | Pending. |
