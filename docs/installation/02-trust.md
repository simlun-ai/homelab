# 02 - Trust

## Working roadmap: encrypted Talos and Kubernetes bootstrap

**Primary milestone:** Install `trust-cp1` as an encrypted Talos single-node Kubernetes cluster on `k8s-aux` (VLAN 10), with system-volume unlock provided by the independent KMS on `ups-aux`. This is the initial installation, **not** a disposable unencrypted bootstrap. OpenBao and other application workloads are later milestones.

**Working branch:** `feat/trust-bootstrap`. Work in small, reviewable commits on this branch. Before each change, agree on the next decision, implement only that slice, test it where possible, and update this roadmap with evidence. Do not mark physical tests complete from configuration or documentation alone. Commit operator-confirmed progress directly to `feat/trust-bootstrap` after each completed milestone.

### Current position

- **Completed prerequisite:** `ups-aux` base bootstrap/hardening and console login verified (2026-11-06). Its KMS service is deployed, with production TLS and locked RPCs verified from the workstation. Live-node authorization and encrypted Pi boot were verified.
- **Decided identity:** cluster `trust`, control-plane node `trust-cp1`, FQDN `trust-cp1.k8s-aux.lundmark.internal`, static IP `10.10.0.10/24`; coordinator `ups-aux` at `10.10.0.5`.
- **Verified firmware boot:** SD-first EEPROM configuration and first UEFI setup boot passed on 2026-11-08. On 2026-11-09 the operator confirmed UEFI Firmware v1.53 and returned to setup after a full power cycle without changing settings. Talos subsequently reached maintenance mode via manual USB selection on 2026-11-09. Disabling the 3 GB RAM cap and cold booting subsequently yielded memory TOTAL `7748` with unchanged UUID and working Ethernet. EEPROM version/exact BOOT_ORDER, other modified settings and automatic USB selection remain unverified.
- **Verified:** Talos cold-booted from the installed two-member OS mirror and unlocked encrypted `STATE` and `EPHEMERAL` through KMS. Kubernetes bootstrap and initial readiness passed.
- **Verified:** [Trust cert-manager and its ACME issuers](trust-cert-manager.md) are installed. Staging DNS-01 issuance passed, and the encrypted OpenTofu state was pushed after a clean plan.
- **Completed (2026-11-21):** [Trust MetalLB](trust-metallb.md) applied with `3 added, 0 changed, 0 destroyed`. The encrypted infrastructure state was [published](https://github.com/simlun-ai/homelab-opentofu-state/commit/1ca23c33c1578d0919fe47eabda72037f062602e).
- **Verified (2026-11-21):** The staged [OpenBao workload](trust-openbao.md) is installed. Its Raft claim is bound, the production-issuer Certificate is ready, and MetalLB assigned `10.10.0.200:443`. The follow-up plan reported no changes and the encrypted workload state was published.
- **Verified (2026-11-21):** [OpenBao initialization and YubiKey-backed unseal](trust-openbao-initialize.md) passed on the staged server. Both wrapped bootstrap records were verified, published, and pinned.
- **Verified (2026-11-21):** The [OpenBao network listener](trust-openbao-network.md) is active through MetalLB. Local DNS and production TLS returned HTTP 200 from the operator workstation. The follow-up plan was clean and encrypted workload state serial 2 was published. Pi and Metal client checks are deferred until their VLANs are set up.
- **Verified (2026-11-22):** A manually triggered OpenBao backup to R2 and restore into the separate rehearsal Helm release passed with matching restic snapshot IDs and Raft digests. The restored instance was sealed. Both CronJobs were enabled and the follow-up OpenTofu plan showed no changes. The [wrapped initial root token](../security/openbao-unseal.md#manual-root-token-use) is retained for occasional manual bootstrap.
- [ ] Verify a [scheduled OpenBao backup and restore pair](trust-openbao-backup-operations.md#verify-a-scheduled-backup-and-restore). Record the run date, matching snapshot ID and digest, and sealed status.

Trust's four 128 GB SSDs have [planned mirror assignments](../inventory.md#mirror-assignments). Use the
`/dev/disk/by-id/ata-*` links in the
[candidate disk inventory](../inventory.md#candidate-disk-inventory) to identify
the physical SSDs. Each link includes the SSD's ATA serial and matched on the
workstation and the Pi. The Pi also reported USB-side links and the same WWID
for all four SSDs. A cold boot confirmed that the ATA links and exact
capacities matched the first discovery. Validate the Talos disk-selection
mechanism separately before installation.

### Next milestone: first Backup KMS boot

- [x] **Verified (2026-11-22):** [Trust workload secret delivery](trust-workload-secrets.md) synced the allowed OpenBao KV entry, received HTTP 403 on the neighboring entry, and recreated the allowed Kubernetes Secret after deletion.
- [x] **Verified (2026-11-22):** [Zot on Trust](trust-zot.md) serves the published ARM64 KMS adapter. Trust pulled the image anonymously by digest and imported the adapter before and after a Zot pod replacement.
- The adapter core passed a local TLS gRPC round trip with disposable OpenBao 2.7.3, including node binding, key rotation, and backend failure.
- [x] **Deployed:** The [Trust-hosted Talos KMS adapter for Backup](trust-talos-kms.md) applied as one new Helm release. The `talos-backup` Deployment rolled out and MetalLB assigned `10.10.0.202:443`. The follow-up plan showed no changes and [encrypted workload state serial 10 was published](https://github.com/simlun-ai/homelab-opentofu-state/commit/66c6160). The first encrypted Backup boot will verify actual unlock.
- [ ] Follow the [Backup Talos runbook](03-backup.md) to boot the first node and verify that encrypted `STATE` and `EPHEMERAL` unlock through that endpoint. Use the Trust rehearsal below for troubleshooting if needed.
- [ ] Return to the remaining Trust installation work after this boot passes. Defer the rest of the Backup installation and the Pi and Metal adapter rollouts.

- [ ] Evaluate Talos [`RegistryMirrorConfig`](https://docs.siderolabs.com/talos/v1.14/configure-your-talos-cluster/images-container-runtime/pull-through-cache), including upstream selection, pre-seeding, fallback and Trust bootstrap recovery. Decide whether Backup, Pi, and Metal share Trust's Zot or run cluster-local instances based on storage and outage requirements.

### Coordinator ACME verification (2026-11-10)

The operator created and wrapped `homelab-ups-aux-dns`, committed the token's
ciphertext in the private repository and updated the parent submodule pointer.
The coordinator tools play passed (`ok=7`, `changed=4`, no failures). With
`acme@simlun.se`, the initial attempt passed issuance but failed during renewal.
After the correction in [PR #23](https://github.com/simlun-ai/homelab/pull/23),
the operator reran the full rehearsal and reported both PASS results: staging
issuance and renewal with the same TLS key, followed by removal of the disposable
ACME workspace. A subsequent query to `1.1.1.1` for
`_acme-challenge.kms.k8s-aux.simlun.se` TXT returned no records.
**Full staging rehearsal acceptance passed.** Durable wrapped ACME state,
production certificates, scheduled renewal and the TCP/TLS listener were pending at that point. See [step 01](01-main-coordinator.md#prepare-cloudflare-and-rehearse-acme)
and the [Cloudflare guide](trust-kms-cloudflare.md#run-the-staging-rehearsal).

### Wrapped state lifecycle verification (2026-11-11)

The operator installed the state helpers and successfully initialized, recovered
and renewed, explicitly recreated, and recovered/renewed the replacement staging
state. The earlier implementation left one current wrapped record and three
archives in the workstation private checkout. This verified real issuance,
YubiKey wrapping and independent recovery of both identities.

The subsequent custody decision removes the requirement to commit these ACME
records: current state and archives belong only on the coordinator. The
[revised instructions](trust-kms-cloudflare.md#move-the-existing-staging-record-to-the-pi)
import the existing record without new issuance or deleting local files. The
coordinator-local import and default recovery/renewal subsequently passed as recorded below. Losing its SD card
uses explicit ACME/TLS recreation; the Cloudflare token remains independently
recoverable from the private repository. Node KMS/Talos authority is unchanged.

Coordinator-local results (2026-11-11): the tools play completed with `ok=11`,
`changed=3`, `unreachable=0`, `failed=0`. YubiKey-verified import succeeded and
left workstation files unchanged. Default recovery fetched the wrapped state
from the Pi, recovered the ACME state and DNS token, renewed the staging
certificate, wrapped and independently recovered the updated state, and
published the ciphertext on the coordinator. The helper reported archival of
the previous ciphertext there. The operator then explicitly recreated the
staging identity, wrapped and independently recovered it, published the
replacement on the Pi with reported archival, and successfully recovered/renewed
that replacement. **The full coordinator-local staging lifecycle passed.**
Production issuance, scheduled renewal and the TLS listener were pending at that point.

### Production certificate attempt (2026-11-11)

The tools play passed on `ups-aux` (`ok=11`, `changed=3`, no unreachable hosts or
failures). Production initialization reported issuance starting, then failed
before wrapping/publication. Native Certbot 4.0.0 reproduction identified a
renewal-file parsing defect: top-level lineage metadata was not accepted by
the original INI check. The fix accepts the native layout and adds safe
stage-specific failure diagnostics. Reinstall the corrected helper and retry
according to the [production guide](trust-kms-cloudflare.md#production-certificate-provisioning-and-recovery).
Production acceptance was pending after this failed attempt; the successful
corrected-helper follow-up is recorded below. Issuance may have completed before
the failed check; avoid repeated production retries.

### Production initialization and recovery verification (2026-11-11)

After the parser fix, the operator's tools play passed (`ok=11`, `changed=1`,
`unreachable=0`, `failed=0`). Production initialization verified the exact
certificate name, matching private key, validity and system-trusted chain,
wrapped and independently recovered the updated state, and stored its
ciphertext on the coordinator. Default recovery then fetched and recovered that
state, checked renewal, reverified the certificate, and reused it because
renewal was not due. The helper reported no state changes to publish, so it
performed no new wrapping/publication or archival for unchanged state.
**Production initialization and certificate-reuse recovery passed.** Actual
production renewal/expiry and live Talos authentication/unlock remain pending.

### Locked production TLS verification (2026-11-11)

The ACME tools play passed (`ok=11`, `changed=0`, `failed=0`). The first
`kms-stage` attempt stopped during the status check because the coordinator's
APT protobuf lacked `GetMessageClass`. After [PR #29](https://github.com/simlun-ai/homelab/pull/29)
switched to `GetMessages`, staging passed (`ok=18`, `changed=2`, `failed=0`)
and status showed KMS locked and TLS disabled.

YubiKey authorization recovered and reused the wrapped production certificate
without republishing ACME state. The listener became active at `10.10.0.5:443`.
The workstation verified system trust and the hostname `kms.k8s-aux.simlun.se`.
Both Seal and Unseal returned `FAILED_PRECONDITION`. Restart produced a new
daemon instance with KMS locked, TLS disabled and no endpoint. The workstation
check failed as expected while TLS was disabled. Reauthorization restored the
listener with the same certificate, and both RPCs again reported KMS locked.
The certificate expires at `2027-02-08T23:55:15Z`.

### Native Talos KMS rehearsal in QEMU (2026-11-11)

Talos v1.14.5 booted in maintenance mode from the verified amd64 ISO and
reported QEMU UUID `5c73da99-dfe7-48b3-8687-5d0b46dbe647`. The guest TCP
probe reached `kms.k8s-aux.simlun.se:443` through QEMU user networking.
The `EPHEMERAL` encryption patch and full VM machine config passed strict
metal validation. The installation used the disposable 16 GiB VirtIO disk
`/dev/vda`.

With the rehearsal key authorized, Talos opened the encrypted `EPHEMERAL`
volume with `KMSKeyHandler` in slot 0, marked `/dev/vda6` ready, and mounted
its mapper device at `/var`. The authenticated Talos API provided the boot
log. The attached log shows the successful open of the encrypted volume;
the initial Seal RPC was not separately captured.

With KMS locked, a later boot log showed Talos attempting to reopen
`EPHEMERAL` on the same partition. Unseal returned
`FailedPrecondition: KMS locked`, the volume entered the failed state,
and Talos retried. The workstation separately verified trusted TLS and
locked Seal and Unseal. The operator had not yet initiated a deliberate
reboot for the locked test when that log was collected. The sequence does
not establish that locking KMS closed an already-mounted volume.

The operator then deliberately rebooted the VM from the same virtual disk
with KMS locked. The fresh boot log showed Unseal in slot 0 return
`FailedPrecondition: KMS locked`. `EPHEMERAL` on `/dev/vda6` moved from
waiting to failed, and subsequent retries received the same response.

The operator removed the runtime systemd override and restarted `ups-aux`'s
KMS service with `serve-locked` and no `--vm-rehearsal` flag. Production TLS
reauthorization reused the existing certificate. Status reported active TLS at
`10.10.0.5:443` and locked KMS. The workstation again verified system trust,
the hostname, and locked responses from both Seal and Unseal.

### Persistent node key enrollment (2026-11-12)

The operator ran `kms-enroll` for `trust-cp1`. The Pi UUID check, YubiKey
wrapping, and independent recovery all passed. The operator pushed the
ciphertext to the private secrets repository and updated the parent submodule
pointer. Coordinator staging passed with `ok=18`, `changed=3`, and no failures
or unreachable hosts. TLS reauthorization reused the existing production
certificate, and the workstation verified system trust, the hostname, and
locked responses from Seal and Unseal.

The two-window check passed on 2026-11-14. With only the enrolled
`trust-cp1` UUID and generation authorized, the probe confirmed rejection of
an unregistered UUID and sealed a public payload. Explicit lock cleared the
window, and both RPCs reported KMS locked over trusted TLS. The operator
recovered the same wrapped key to open a separate window and unsealed the
original payload. The final lock reported `state: locked`, `remaining: 0`,
and an empty authorization list. This exercised explicit lock and key reuse;
live expiry and Pi boot with encrypted `STATE` remain to be verified.

### Pi installation preflight

The public render contains KMS-backed LUKS2 for `STATE` and `EPHEMERAL`.
The separate [RAID1 draft](../../clusters/trust/talos/experiments/trust-cp1-raid1.yaml)
selects the Intenso and Silicon Power SSDs by their exact ATA links and
targets the resulting `md-name-talos:boot` device. The [mirror assignments](../inventory.md#mirror-assignments) record the Fanxiang and Patriot ZFS drives separately; neither ATA link matches the RAID selector. Repeat live discovery if disk assignments or hardware change. Keep the UEFI card and installer media distinct from the two
OS SSDs.

Run the offline preflight from the homelab root:

```sh
make -C clusters/trust validate
make -C clusters/trust install-config-rehearse
```

The rehearsal generates disposable credentials in a pipe and validates the full
config with both patch sets. It uses a sentinel legacy install disk and sends
nothing to the Pi. The RAID draft includes an unattended installer, so keep
the assembled config offline until explicitly ready to install.

After the disposable rehearsal passes, validate the configuration using the
existing wrapped Trust bootstrap identity:

```sh
make -C clusters/trust install-config-validate
```

Touch the YubiKey to recover the existing record. The helper uses the real Trust
API endpoint, public render, and pinned RAID1 installer draft. It keeps
plaintext in memory and reports only validation status. Leave the KMS key
window closed for this operation.

For pre-`STATE` networking, Talos v1.14.5 accepts a kernel
[`ip=` argument](https://github.com/siderolabs/talos/blob/v1.14.5/website/content/v1.14/reference/kernel.md)
with IP, gateway, interface, resolver and NTP address. The public
[candidate schematic](../../clusters/trust/talos/experiments/trust-cp1-early-network.schematic.yaml)
uses the observed `enabcm6e4ei0` interface, `10.10.0.10/24`,
`10.10.0.1` for the route and resolver, and Cloudflare NTP at
`162.159.200.1`. The NTP choice is provisional. Confirm the coordinator's time
source and verify NTP reachability from the Pi before selecting it.

First boot test media with the candidate arguments and no install config.
Check the effective kernel command line, address, route, DNS, fresh time
sync, and KMS TCP reachability. Confirm the selected ARM64 installer carries
the same arguments into the installed boot path before relying on it for
encrypted `STATE`. The RAID draft selects the installer built from the same Image Factory
schematic as the tested ISO and pins its ARM64 manifest digest.
The definitive check is an installed boot from the mirror with the USB
installer removed and the Trust KMS window authorized.

### Verify the installer boot arguments

Talos v1.14.5 unattended installation tells GRUB to use the command line
embedded in the installer image's UKI. The installer ISO and the installed
boot image are separate assets. The ARM64 manifest and UKI layer matched
their registry digests, and the UKI's `.cmdline` section contained the exact
`ip=` argument from the tested ISO schematic. To repeat the check, this
example uses Docker and LLVM's `llvm-objcopy` on the workstation. It extracts
an image file without running the installer.

```bash
(
  set -euo pipefail
  image='factory.talos.dev/metal-installer/c388d7fe0077e7d054f4a4d76fe7bb0a7fba9741b0ad2569be0a410b2c54f940:v1.14.5@sha256:3d7a3a87e00e553b754a53a08a6890a7b19e00b7bdae28de763c357ee35c24dc'
  schematic=clusters/trust/talos/experiments/trust-cp1-early-network.schematic.yaml
  expected=$(sed -n 's/^    - \(ip=.*\)$/\1/p' "$schematic")
  test -n "$expected"
  work=$(mktemp -d)
  container=
  trap 'if test -n "$container"; then docker rm "$container" >/dev/null; fi; rm -rf -- "$work"' EXIT

  docker pull --platform linux/arm64 "$image"
  container=$(docker create --platform linux/arm64 "$image")
  docker cp "$container:/usr/install/arm64/vmlinuz.efi" "$work/vmlinuz.efi"
  llvm-objcopy --dump-section ".cmdline=$work/cmdline" \
    "$work/vmlinuz.efi" "$work/copied.efi"
  tr -d '\000' < "$work/cmdline" | tr ' ' '\n' | grep -Fx -- "$expected"
  echo 'PASS: ARM64 installer UKI contains the tested early networking argument.'
) && make -C clusters/trust install-config-rehearse
```

The exact match checks addressing, gateway, interface, DNS and NTP as a single
argument. A cold boot from the installed mirror is still needed to verify the
effective arguments and KMS-backed `STATE` unlock on the Pi.

### Pi early boot rehearsal (2026-11-14 UTC)

- The operator's `install-config-rehearse` verified the pinned clients,
  checked render freshness, and passed strict metal validation of the full
  disposable RAID1 and KMS configuration.
- `ups-aux` reported a synchronized clock via systemd-timesyncd, using
  `2.debian.pool.ntp.org` at the time of the check. The Pi separately tested
  the candidate Cloudflare NTP address `162.159.200.1`.
- Image Factory schematic
  `c388d7fe0077e7d054f4a4d76fe7bb0a7fba9741b0ad2569be0a410b2c54f940`
  produced the custom Talos v1.14.5 ARM64 rehearsal ISO. The USB write matched
  the downloaded ISO byte for byte over the image length.
- Before applying an install config, the Pi reported the intended `ip=`
  argument, `10.10.0.10/24` on `enabcm6e4ei0`, a boot default route and a
  resolver at `10.10.0.1`, and `synced: true`.
- A temporary five-minute TCP probe from that boot reached
  `kms.k8s-aux.simlun.se:443` with `success: true` and an empty
  `lastError`. Installed-media argument persistence, TLS verification
  and encrypted volume unlock were outside this rehearsal.

### Production Talos identity and install validation

The operator's offline rehearsal passed with the digest-pinned ARM64 installer.
The first production validation stopped before config generation because the
expected Talos bootstrap record was unavailable locally. The operator
initialized the production identity, then successfully recovered it and ran
`install-config-validate` against the full RAID1 and KMS configuration.
The operator committed and pushed the wrapped record in the private submodule
and pushed the updated parent pointer. Installation and Pi cold boot are the
next hardware checks.

### Apply the initial Trust install configuration

Use the custom USB ISO already tested in maintenance mode at `10.10.0.10`.
Keep the Pi console visible. The apply target checks the reported maintenance
UUID against the enrollment, recovers the existing Talos identity, then
assembles and strictly validates the config before sending those same bytes.
The maintenance API uses encrypted transport without server authentication;
use the trusted management path to the Pi. The UUID check helps catch a
wrong target.

Open a fresh KMS window immediately before applying:

```bash
make -C clusters/trust kms-window-open &&
  make -C clusters/trust install-config-apply
```

The apply starts the unattended installation on the assigned OS mirror.
A successful apply acknowledgment means Talos accepted the config. Watch the
console for installation completion. If acknowledgment is missing, inspect the
console before retrying because the installer may already be running.

After installation completes, boot from the mirror with the USB installer
removed and the UEFI card in place. Keep a valid KMS window for that boot.
Verify that Talos boots at the planned address and opens both encrypted system
volumes. Close the KMS window after verification. Kubernetes bootstrap is the
following milestone.

### Installed Pi cold boot and encrypted unlock (2026-11-15)

Talos accepted the install configuration and announced a reboot. The console
stopped at `psci: CPU3: killed (polled 0 ms)`. The operator power-cycled the
Pi with the USB installer removed and the UEFI microSD card in place. The
installed system answered at `10.10.0.10` and accepted the authenticated
Talos admin client.

The installed kernel command line contained the expected early network
argument. Linux assembled `/dev/md127` with two of two RAID1 members.
`STATE` on `/dev/md127p3` initially reported missing encrypti…15019 tokens truncated…also checked. No card was written or Pi booted by
these checks. The operator subsequently completed EEPROM/card preparation and
reached UEFI setup as recorded below.

### Experiment record and acceptance checks

Record the repository revision, EEPROM and EDK2 versions/settings, Talos image/schematic, assigned disk identities, results, and remaining issues here. Do not mark these complete until tried.

- [x] Operator completed SD-first EEPROM configuration (2026-11-08).
- [x] Prepared firmware card reaches UEFI setup (2026-11-08).
- [x] UEFI Firmware v1.53 confirmed; setup reached again after a full power cycle, with no settings changes (2026-11-09).
- [x] UEFI RAM-cap disable remained effective after a full cold boot (2026-11-09); other deliberately changed settings need separate verification.
- [x] Generic Talos ARM64 ISO reaches maintenance mode via manual USB selection in UEFI Boot Manager (2026-11-09).
- [ ] Automatic selection of the intended USB installer boot entry is verified, if needed for this experiment.
- [x] Record initial node UUID, running Talos version, Ethernet/MAC/link, limited-memory baseline and synchronized-time status (2026-11-09).
- [x] Repeat UUID, physical interface/MAC, Ethernet link, memory and synchronized-time observations after disabling the RAM cap and cold booting (2026-11-09).
- [x] Validate the corrected Pi LinkConfig and public render offline with pinned Talos tooling (2026-11-09).
- [x] Verify the KMS A record through the UniFi resolver from the operator workstation (2026-11-09).
- [x] Rehearse the Pi's static address, default route, DNS and timed DHCP rollback in maintenance mode (2026-11-09).
- [ ] Verify fresh time sync and KMS connectivity during actual pre-STATE boot. UUID stability across other firmware/reinstall changes remains unverified.

The temporary `TCPProbeConfig` resolved `kms.k8s-aux.simlun.se` to
`10.10.0.5` and timed out connecting to TCP 443. Its failed status accounts
for the dashboard's connectivity warning. Talos reported synchronized
time, with the status last updated before the static configuration took
effect. Pi-side TLS, KMS authentication and encrypted STATE unlock remain pending.
- [x] Inspect candidate SSDs and existing signatures read-only on the workstation (2026-11-09).
- [x] Record the sampled USB-to-SATA adapter model and verify that Talos detects all four SSDs together with matching ATA links (2026-11-09).
- [x] Recheck all four ATA links and capacities after a cold boot (2026-11-09).
- [x] Record the selected OS and data mirror members by ATA link in [inventory.md](../inventory.md#mirror-assignments).
- [x] Verify that Talos maintenance mode reports both OS candidates as whole disks (2026-11-09).
- [x] Generic Talos ARM64 live environment uses the increased RAM after removing the limit: TOTAL `7748` (2026-11-09).
- [ ] Generic Talos ARM64 live environment sees and operates with the selected disks/adapters.
- [ ] Firmware card does not confuse Talos EFI/system-disk discovery.
- [x] Operator validated the standalone RAID1 draft offline with the pinned client in strict metal mode (2026-11-09).
- [ ] Installation onto MD RAID1 with metadata `1.0` completes without META deletion or copying firmware.
- [x] Installed Talos cold boots with installation media removed (2026-11-15).
- [x] Cold boot succeeds with either OS disk disconnected, tested separately after restoring mirror health between tests (2026-11-16).
- [x] Rehearse replacing one OS SSD (verified 2026-11-17). Boot from the surviving member, verify the replacement's ATA link and size, update only the RAID member selector, then verify a two-member array, completed resync and boot from the replacement. Talos reconciliation adds matches. Removing the old link alone does not remove a member.
- [ ] Talos upgrade and subsequent cold boot work.
- [ ] Independent coordinator KMS unlock works, including a cold startup.

Results (2026-11-08): **First UEFI setup boot passed.** The operator completed
the Raspberry Pi Imager SD Card Boot EEPROM step, then used a different card
(reported as 14.8 GiB at `/dev/sda` on `simlun-x1`) for the documented pftf/RPi4
v1.53 firmware preparation and reported reaching UEFI setup. `/dev/sda` is a
workstation observation, not a persistent card identifier. Card model/exact byte
capacity and EEPROM version have not been captured. The exact BOOT_ORDER
value and individual ACPI/RAM values were not reported.

Follow-up (2026-11-09): the operator read **UEFI Firmware v1.53** from setup,
powered the Pi off fully, then pressed **Esc** at the Pi logo after powering on
and returned to UEFI settings. No UEFI settings had been changed. This verifies
repeatable cold boot into setup, not persistence of modified settings.

Talos live boot (2026-11-09): after preparing the separate USB installer from the
pinned generic ARM64 ISO procedure, the operator manually selected it in UEFI
Boot Manager. Talos reached maintenance mode and displayed DHCP address
`10.10.0.246` on the intended network. This is a temporary discovery address,
not application of the planned static `10.10.0.10` configuration. Automatic USB
selection was not verified by this boot. The read-only baseline below subsequently
captured running version, UUID, interface/MAC, memory and time state. No machine configuration, disk installation or Kubernetes
bootstrap was performed in this step.

### Read-only live baseline (2026-11-09)

The operator queried the maintenance API at DHCP `10.10.0.246` using the scoped
client. The observations describe the live environment, not applied production
configuration or installed/encrypted Talos.

| Observation | Reported value |
| --- | --- |
| Client/server | Talos `v1.14.5`, SHA `dad8d3ed`; client Linux amd64, server Linux arm64 |
| Hardware | Raspberry Pi Foundation, Raspberry Pi 4 Model B; SMBIOS version `D03115` |
| Serial | `1000000089261F6E` |
| Firmware | `UEFI Firmware v1.53` |
| Hardware UUID | `00d03115-0000-0000-1000-000089261f6e` |
| Physical Ethernet | `enabcm6e4ei0`, alternative name `enxd83add37d639`, driver `bcmgenet` |
| Permanent/current Ethernet MAC | `d8:3a:dd:37:d6:39` |
| Link | Up, 1000 Mbit/s, full duplex; MTU 1500 |
| Memory | `talosctl memory`: TOTAL `2848`, AVAILABLE `2483`; initial RAM-limit settings unchanged |
| Time status | `synced: true`, `syncDisabled: false`, `epoch: 1` |

The memory total is consistent with the initial UEFI 3 GB cap; nominal physical
inventory remains 8 GB; the subsequent full-memory result is recorded below. Initial
resource timestamps were `2026-08-31`, while TimeStatus was subsequently updated
at `2026-11-08T23:20:01Z`. This is consistent with a clock correction after boot;
it does not establish when time became usable relative to encrypted STATE/TLS.

**Network configuration:** the public LinkConfig targets the observed physical
link `enabcm6e4ei0`. The static address, DNS resolution and routing still
require live verification before relying on them for KMS unlock.

### Full-memory cold-boot verification (2026-11-09)

The operator disabled the UEFI 3 GB RAM limit, saved the change and cold booted
the same Talos live media. Read-only queries again reached DHCP `10.10.0.246`.

| Check | Result after cold boot |
| --- | --- |
| Firmware | `UEFI Firmware v1.53` |
| UUID | Unchanged: `00d03115-0000-0000-1000-000089261f6e` |
| Ethernet | Same `enabcm6e4ei0`, alternative `enxd83add37d639`, MAC `d8:3a:dd:37:d6:39`, driver `bcmgenet` |
| Link | Up, 1000 Mbit/s, full duplex, MTU 1500 |
| Memory | TOTAL increased from `2848` to `7748`; AVAILABLE `7203` |
| Time | `synced: true`, `syncDisabled: false`, `epoch: 1`; updated `2026-11-08T23:34:44Z` |

The increased RAM is available after the cold boot, confirming the RAM-cap
change remained effective. UUID and physical Ethernet continuity passed for
this observed settings change; this does not establish UUID stability across
firmware upgrades or reinstall. Successful live Ethernet/time checks do not
establish pre-STATE/KMS readiness or disk/adapter compatibility.

### Workstation disk inspection (2026-11-09)

The operator inspected four candidate SATA SSDs individually on `simlun-x1`.
Each appeared as `/dev/sda` with `119.2G` displayed by `lsblk`, and the output
listed no partitions or mountpoints. `wipefs --no-act` reported a DOS/MBR
signature at `0x1fe` on the Intenso and no signatures on the other three.
The [candidate disk inventory](../inventory.md#candidate-disk-inventory) records
the exact ATA models, serials and workstation device links.

Use the [mirror assignments](../inventory.md#mirror-assignments) to identify
the intended OS targets. Verify the physical interface and planned address
before applying a machine configuration.

If the firmware card fails, power off and recreate it from the pinned archive; recheck SD-first EEPROM boot. Preserve the previous boot media/settings for rollback. Reverting a Talos disk installation needs its own recovery procedure before destructive installation is attempted.

## Stage the ZFS extension on Trust

The [ZFS schematic](../../clusters/trust/talos/experiments/trust-cp1-zfs.schematic.yaml)
adds `siderolabs/zfs` and retains the Pi's verified early network argument.
Regenerate the schematic ID and the pinned ARM64 installer reference from the homelab root:

```sh
make -C clusters/trust installer-image \
  SCHEMATIC=talos/experiments/trust-cp1-zfs.schematic.yaml
```

The target registers the public schematic with Image Factory and writes the
returned ID beside it in `trust-cp1-zfs.schematic.id`. Image Factory hashes
its canonical representation, so a SHA-256 of the source file can differ.
It reads the Talos release from `versions.yaml`, selects the Linux ARM64
manifest, verifies its SHA-256, and writes the digest-only reference to
`trust-cp1-zfs.schematic.arm64.image`. Talos v1.14.5 pulls an image specified
with both tag and digest under the digest-only name, then fails to find it
under the original name in containerd. If that reference changes, inspect
the new installer UKI before upgrading.

Use the ARM64 installer for the same Talos v1.14.5 release. This is an
in-place upgrade of the installed OS mirror. Keep the current installer
reference in the initial-install draft until the upgrade and boot pass.

Before upgrading, confirm the mirror shows `[2/2] [UU]` with no rebuild
in progress, and that Kubernetes is healthy. Keep the UEFI microSD and
both OS SSDs attached, and the USB installer removed. Verify a fresh KMS
window is active for `trust-cp1` before starting the upgrade. Keep the
console visible through the single-node outage.

Use the existing in-memory Talos admin credential flow. Pass the following
arguments to the authenticated command:

```sh
image=$(cat clusters/trust/talos/experiments/trust-cp1-zfs.schematic.arm64.image) &&
  talosctl upgrade --endpoints 10.10.0.10 --nodes 10.10.0.10 \
    --image "$image" \
    --reboot-mode powercycle
```

Preserve the existing `EPHEMERAL` volume during routine upgrades. With pinned
Talos v1.14.5, use the standard in-place upgrade above. The deprecated
`--preserve` flag applies only to the legacy upgrade API. Check the flags
again when changing Talos versions. After the ZFS pool is in service, verify
its local key file and pool readiness after each upgrade. If a reset or
reinstall removes `EPHEMERAL`, restore the key from the existing wrapped
record before importing and unlocking the data pool.

The power-cycle reboot mode bypasses kexec. If the command loses its
connection, inspect the console and node state before retrying. After
boot, verify the installed command line, both encrypted volumes, and
mirror and Kubernetes readiness.

Confirm `talosctl get extensions` lists ZFS before adding the public
[ZFS module document](../../clusters/trust/talos/experiments/trust-cp1-zfs-module.yaml).
Apply that document to the live machine configuration via authenticated
`talosctl patch machineconfig`, starting with a dry run. If Talos requires
a reboot for the module change, keep the same boot prerequisites and
verify `/dev/zfs` after reboot. The extension and module smoke check is
complete when ZFS is loaded and the node is healthy. Then lock the KMS
window. Pool creation and key installation are separate steps.

### ZFS extension and module verification (2026-11-17)

The operator regenerated the schematic ID and ARM64 installer reference with
no diff, then verified the OS mirror and Kubernetes were healthy. The initial
upgrade pulled the image but failed to look it up under its tag-plus-digest
name. The digest-only retry completed, drained and uncordoned the node, and
reported a passing post-check.

The Pi initially booted the old schematic. The operator then selected
`talos-v1.14.5~1.efi` in systemd-boot. Talos reported the expected schematic
`6a913c641507a4fc7ff51c595e607d39b4fdfcd80f7cbb6581fe4517a7c21cf3`
and ZFS `2.4.4-v1.14.5`. The module patch dry run showed only the addition
of `KernelModuleConfig` for `zfs`. The live apply succeeded without a reboot.
The module appeared as live in `/proc/modules` and `/dev/zfs` was present.
Automatic boot selection and data-pool setup remain pending.

### Open question: console-free boot and upgrades

Configure and test the Pi's UEFI boot order with both OS SSDs ahead of PXE.
Investigate why a same-version extension upgrade reported a successful post-check
while the Pi booted the old schematic, and verify systemd-boot selects the intended
UKI without manual intervention. Include a remote post-upgrade check of the running
schematic and extensions. Out-of-band recovery remains a separate question.

### Enroll the Trust ZFS key

The Patriot/Fanxiang mirror will use native encryption at the root dataset
of `trust-data`. Enroll its independent key from the workstation before
creating the pool. Initialize the private wrapped-record submodule and
connect the YubiKey, then run:

```sh
make -C clusters/trust zfs-key-enroll
```

Touch the YubiKey when prompted for wrapping and again for independent
recovery. The helper checks that the recovered 32 bytes match the generated
bytes in memory. The wrapped record is
`secrets/wrapped/trust-data-zfs-r1.json`. If it already exists or enrollment
was interrupted after publication, use `make -C clusters/trust zfs-key-verify`
to recover the existing record and check its length. Commit and push the
ciphertext in the private submodule and update the parent pointer before
using the key. These commands work independently of the Pi and OpenBao.

On 2026-11-17, the operator enrolled the key, independently recovered the
same 32 bytes with the YubiKey, pushed the wrapped record to the private
submodule, and pushed the updated parent pointer.

### Install the Trust ZFS key on the Pi

With `trust-cp1` ready, the private submodule initialized, and the YubiKey
connected, run from the homelab root:

```sh
make -C clusters/trust zfs-key-install
```

Touch the YubiKey for the Talos admin identity and again for the enrolled ZFS
key. A temporary receiver pod on `trust-cp1` mounts only
`/var/lib/trust-zfs/keys` from the host. The receiver checks the mount against
the LUKS2 `EPHEMERAL` mapper before accepting bytes and repeats that check
during delivery. The key travels over authenticated Kubernetes exec stdin.
The process arguments contain the public receiver code and action name;
the key bytes are supplied through a separate stdin pipe.
The helper creates the file without replacing an existing entry, verifies
root ownership and mode `0600`, and accepts an existing file only if the bytes
and metadata match. It deletes the temporary namespace after the operation.

Expect `PASS: root-only ZFS key verified on encrypted EPHEMERAL.` and namespace
deletion. If the command is interrupted, inspect the temporary
`trust-zfs-key-*` namespace and rerun installation to verify the file. Keep
the wrapped record for recovery after an OS rebuild.

On 2026-11-17, the operator ran `zfs-key-install` on `trust-cp1`. The receiver
confirmed the destination was on encrypted `EPHEMERAL` before recovering the
wrapped ZFS key. Delivery verified the root-owned `0600` file at
`/var/lib/trust-zfs/keys/data.key`, and the temporary namespace was deleted.

### Create the encrypted Trust data mirror

On 2026-11-18, Talos reported both assigned data SSDs at 128,035,676,160
bytes with no discovered partitions or volume signatures. The operator
created the pool manually from a temporary privileged pod on `trust-cp1`
with the Talos host mounted at `/host`. Run pool creation only for the
initial setup of these assigned disks.

```sh
chroot /host zpool create -o ashift=12 -m none \
  -O encryption=aes-256-gcm -O keyformat=raw \
  -O keylocation=file:///var/lib/trust-zfs/keys/data.key \
  trust-data mirror \
  /dev/disk/by-id/ata-Fanxiang_S101_128GB_26060780625001902 \
  /dev/disk/by-id/ata-Patriot_P220_128GB_P220HHBB251201003962
```

`zpool status -P trust-data` showed `mirror-0` and both `-part1`
members `ONLINE`, with zero read, write, and checksum errors.
`zfs get encryption,encryptionroot,keyformat,keylocation,keystatus,mountpoint trust-data`
showed `aes-256-gcm`, encryption root `trust-data`, raw key format,
the expected file URI, `keystatus=available`, and `mountpoint=none`.
The temporary namespace was deleted.

### Verify Trust data storage after a reboot

Open the Trust KMS window and reboot into the ZFS-enabled EFI entry. Once
`trust-cp1` returns, check `zpool status -P trust-data` and
`zfs get keystatus,keylocation trust-data` before manually loading the key.
Pool import and key availability are separate checks. The extension runs
`zpool import -fal`, and OpenZFS documents `-l` in terms of datasets it
attempts to mount. Record the observed behavior with the root mountpoint
set to `none`. Close the Trust KMS window after the node has recovered.

On 2026-11-18, after rebooting into the ZFS-enabled EFI entry, `trust-cp1`
returned to `Ready`. The status check ran before any manual key load.
`trust-data` and both ATA mirror members were `ONLINE` with zero read,
write, and checksum errors. ZFS reported `keystatus=available` with the
local key URI and `mountpoint=none`, confirming automatic import and
local key loading for this configuration. The temporary namespace was
deleted.

### Rehearse Trust data recovery on the workstation

1. On `trust-cp1`, create `trust-data/recovery-check` with
   `canmount=noauto` and `mountpoint=/var/lib/trust-zfs/recovery-check`.
   Confirm that its encryption root is `trust-data`. Mount it explicitly,
   write a non-secret fixture, save its SHA-256 outside the pool, then
   unmount it. Use the fixture for the boot and workstation checks.
2. After the Pi reboot check, cleanly export only `trust-data` and shut
   down the Pi before moving the two data SSDs. Leave the OS mirror and
   UEFI microSD in the Pi.
3. On a workstation with compatible OpenZFS, verify the two ATA partition
   links and import only the test pool with `-N`, `readonly=on`, and a
   temporary alternate root. Confirm the pool and both members are online.
   Confirm the key is unavailable before recovery.
4. Recover the original raw key with the YubiKey from the private wrapped
   record. Supply it to `zfs load-key` through a memory-backed input and
   keep the pool's recorded key location. Explicitly mount the test dataset
   read-only and compare the fixture's SHA-256 with the value saved before
   removing the drives.
5. Unmount the test dataset and export the pool before disconnecting the
   drives. Return them to the Pi and verify the mirror is online.

On 2026-11-18, the operator wrote and unmounted the fixture on
`trust-data/recovery-check`. The dataset inherits encryption from
`trust-data`. The SHA-256 of `fixture.txt` is
`3f5b529e80156a0d7348d8f1ae8c7a68d06381dcd8e7415a23a25ebc70660b56`.

#### Read-only unlock example

Run from the homelab root with the private wrapped-record submodule and the
HSM tools available. First import only `trust-data` with
`zpool import -N -o readonly=on -R <temporary-altroot>` and the two verified
ATA partition links as described above. The example loads the original raw
key from an anonymous memory file passed as standard input to `zfs load-key`.
The `-L` override applies only to that invocation. ZFS mounts the dataset
under the alternate root.

```sh
(
  set +x
  set -e
  sudo -v
  test "$(sudo -n zpool get -H -o value readonly trust-data)" = on

  "${HSM_VENV:-$HOME/.local/share/homelab/venvs/hsm}/bin/python" -I -B - <<'PY'
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path("scripts").resolve()))
import trust_talos_recovery as recovery
import trust_zfs_key as zfs_key

recovery.secrets.harden()
recovery.secrets.require_private_repository(record=zfs_key.RECORD)
unwrap = str(Path(sys.executable).with_name("homelab-unwrap"))
print("Touch the YubiKey to recover the original Trust ZFS key.", flush=True)
with recovery.config.memory_file(zfs_key.recover(unwrap)) as fd:
    subprocess.run(
        ["sudo", "-n", "zfs", "load-key", "-L", "file:///proc/self/fd/0", "trust-data"],
        stdin=fd, check=True,
    )
PY

  sudo -n zfs mount -o ro trust-data/recovery-check
)
```

After reading the dataset, unmount it and export the pool before unplugging
the drives.

```sh
sudo zfs unmount trust-data/recovery-check &&
  sudo zpool export trust-data
```

#### Workstation recovery result

On 2026-11-18, the workstation imported the two ATA members as an
`ONLINE` mirror with `readonly=on` and `cachefile=none`. The workstation
used OpenZFS userspace 2.1.5 and kernel module 2.2.2. Before recovery the
fixture was unmounted and its key was unavailable. The operator recovered
the original key with the YubiKey, mounted the fixture read-only, and
matched the recorded SHA-256. The fixture was unmounted and
`trust-data` exported successfully.

After both SSDs were returned to the Pi, `trust-cp1` reached `Ready`.
`trust-data` and both ATA members were `ONLINE` with zero read, write,
and checksum errors. The pool reported `readonly=off` and
`keystatus=available` with `file:///var/lib/trust-zfs/keys/data.key`.
This completed the workstation recovery rehearsal. The temporary
verification namespace was deleted.

### Rehearse recovery after local ZFS key loss

On 2026-11-18, the operator exported `trust-data` and moved
`data.key` aside on encrypted `EPHEMERAL`. The pool imported `ONLINE`
without mounting datasets and reported `keystatus=unavailable`. Loading
the key from the configured URI failed because the file was missing.

The operator ran `make -C clusters/trust zfs-key-install`. The helper
verified the destination was on encrypted `EPHEMERAL`, recovered the
original key with the YubiKey, and verified the root-owned `0600` file.
`zfs load-key trust-data` loaded the key using the normal local URI. The
operator mounted the fixture read-only and matched the SHA-256 recorded
above. The fixture was unmounted, the restored key matched the temporarily
moved file byte for byte, and the temporary copy and namespace were
removed.

### Inspect Trust ZFS properties with Talos debug

On 2026-11-18, the operator used `talosctl debug` over the authenticated
Talos API to run the installed ZFS tool. For one-off host commands such as
checking ZFS properties, this is the simpler path. The standard debug
container exposes the host under `/host`, so the check needs only the Talos
admin identity and a pinned debug image.

The following command uses the current Trust Talos credentials and the
pinned image referenced by `scripts/trust_zfs_key_install.py` as
`debug_image`. Keep the input stream open through command completion when
calling it from a non-interactive wrapper.

```sh
talosctl --endpoints 10.10.0.10 --nodes 10.10.0.10 debug --namespace cri \
  --args '/usr/sbin/chroot,/host,/usr/local/sbin/zfs,get,-r,compression,trust-data' \
  "$debug_image"
```

Both `trust-data` and `trust-data/recovery-check` reported
`compression=on` with source `default`. Keep the OpenZFS default for these
experiments. At the next planned dataset creation, choose and explicitly
set the compression algorithm.

### Install ZFS LocalPV

Use the [Trust OpenTofu bootstrap runbook](../../runbooks/trust-opentofu-bootstrap.md)
to enroll and verify the wrapped state key, prepare the private sibling
state checkout, review the infrastructure plan, and install ZFS LocalPV
v2.11.2.

On 2026-11-19, the operator ran the first live `tofu-plan`. It showed
`3 to add, 0 to change, 0 to destroy`. The additions were the
`openebs-zfs` namespace, the `zfs-localpv` Helm release at v2.11.2 on
`trust-cp1`, and the non-default `trust-zfs-rehearsal` StorageClass.
The class targets `trust-data` with native ZFS datasets,
`WaitForFirstConsumer`, and the rehearsal's `Delete` reclaim policy.

The first apply created the `openebs-zfs` namespace. Helm timed out
waiting for the controller because `trust-cp1` has the
`node-role.kubernetes.io/control-plane:NoSchedule` taint. Helm's atomic
cleanup removed the release workloads. A subsequent YubiKey recovery
failed during state persistence, and OpenTofu retained `errored.tfstate`
on tmpfs. Recover that state before retrying. The Trust node patch
removes the control-plane scheduling taint through Talos so `trust-cp1`
can run workloads as a single-node cluster. The bootstrap runbook
covers previewing and applying the patch to the installed node.

On 2026-11-19, the operator recovered the encrypted emergency snapshot
into the Trust state checkout. The Talos scheduling preview showed only
the removal of the control-plane taint. Talos applied the patch without
a reboot. The subsequent node check and OpenTofu plan passed, with
`2 to add, 0 to change, 0 to destroy`. OpenTofu recognized the existing
`openebs-zfs` namespace, then installed ZFS LocalPV v2.11.2 and created
`trust-zfs-rehearsal`.

The operator verified the encrypted Trust state envelope at serial 3
and committed it locally in the private sibling checkout (`41c016f`).
A fresh OpenTofu plan read the state and reported no changes.

### Verify LocalPV persistence and reclamation

On 2026-11-19, a disposable 1 GiB claim using
`trust-zfs-rehearsal` was provisioned on `trust-cp1`. The writer
stored a fixture and a replacement pod read the same bytes through
the same claim.

A Talos debug check confirmed that the backing dataset under
`trust-data` was a ZFS filesystem with `encryption=aes-256-gcm`,
`encryptionroot=trust-data`, and `compression=on` from the OpenZFS
default. Deleting the reader and the claim reclaimed the Kubernetes
PV. A follow-up Talos debug listing confirmed that LocalPV removed
the matching ZFS dataset and that the pool and recovery fixture
remained present. The test namespace was deleted.

### Prepare OpenBao's production storage

The Trust infrastructure root defines `trust-zfs-retain` as a
non-default LocalPV StorageClass for persistent data. It uses ZFS
filesystems on `trust-data`, inherits its encryption, explicitly sets
`compression=lz4`, and retains the backing volume when the claim is
deleted. Follow the [production retention rehearsal](../../runbooks/trust-opentofu-bootstrap.md#5-verify-the-production-retention-policy)
before pointing OpenBao at the class.

On 2026-11-19, the operator reviewed the OpenTofu plan for
`trust-zfs-retain` and applied it on Trust. The plan and apply each
reported a single addition with zero changes or deletions. The operator
published the updated encrypted state and the local state backup ignore
rule in the private sibling checkout.

A disposable 1 GiB claim using `trust-zfs-retain` bound on `trust-cp1`.
Its consumer wrote and read back a fixture. Talos debug confirmed the
backing dataset used `aes-256-gcm` under the `trust-data` encryption
root and reported `compression=lz4` with source `local`.

Deleting the consumer and claim moved the PV to `Released` while the
matching ZFS dataset remained present. For cleanup, the operator
changed only the released scratch PV's policy to `Delete`. CSI reclaimed
that PV and Talos debug confirmed its dataset was gone. The
`trust-data` pool and recovery fixture remained present, and the test
namespace was deleted.

## Later platform and service milestones

- [ ] Deploy Headlamp on Trust and verify it can display the Trust cluster's resources.
- [ ] Validate Talos installation, boot, MD RAID1, and KMS encryption on the assigned OS disks; implement the pinned tooling and Trust bootstrap configuration.
- [ ] Document manual encrypted ZFS mirror preparation and deploy the planned platform services and OpenBao, including workstation/YubiKey unseal support. During ZFS setup, configure normal unlock from a local key file on an encrypted Talos system volume and rehearse recovery from the YubiKey-wrapped copy before relying on it. Preserve the ZFS data disks when rebuilding the OS.
- [ ] Verify cold startup, scheduled Raft snapshot backups, and the required restore paths; record results and update the recovery guide.

References: [Trust architecture](../clusters.md#trust), [hardware and disks](../inventory.md#trust), [repository layout](../layout.md#common-cluster-layout), [OpenBao unseal](../security/openbao-unseal.md), [backup and recovery](../backup-and-restore.md).
