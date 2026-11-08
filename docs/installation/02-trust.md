# 02 - Trust

## Working roadmap: encrypted Talos and Kubernetes bootstrap

**Primary milestone:** Install `trust-cp1` as an encrypted Talos single-node Kubernetes cluster on `k8s-aux` (VLAN 10), with system-volume unlock provided by the independent KMS on `ups-aux`. This is the initial installation, **not** a disposable unencrypted bootstrap. OpenBao and other application workloads are later milestones.

**Working branch:** `feat/trust-bootstrap`. Work in small, reviewable commits on this branch. Before each change, agree on the next decision, implement only that slice, test it where possible, and update this roadmap with evidence. Do not mark physical tests complete from configuration or documentation alone.

### Current position

- **Completed prerequisite:** `ups-aux` base bootstrap/hardening and console login verified (2026-11-06). Its additional KMS service is not yet implemented.
- **Decided identity:** cluster `trust`, control-plane node `trust-cp1`, FQDN `trust-cp1.k8s-aux.lundmark.internal`, static IP `10.10.0.10/24`; coordinator `ups-aux` at `10.10.0.5`.
- **Planned, not verified:** Pi 4 UEFI firmware-card boot, Talos installation, OS SSD MD RAID1, KMS-backed `STATE`/`EPHEMERAL` encryption, and Kubernetes bootstrap.
- **Current next step:** Verify the new disposable wrapped recovery rehearsal on the workstation, integrating protected configuration generation and 24-hour client issuance. The production API endpoint and Talos recovery authority are agreed; DNS resolution and the disposable protected issuer rehearsal are verified on the workstation. Then settle initial-installation versus ongoing-operation entry points (Point 5). Verify Pi networking and early-boot behavior before installing onto disks.

### Milestone tracker

| # | Stage | Exit criteria | Status |
| --- | --- | --- | --- |
| 0 | Identity and working baseline | Names/IP/roles and owning files agree; branch and roadmap established | In progress — baseline recorded; branch created |
| 1 | Provisioning contract and scoped tools | Agree on declarative node/disk schema, `clusters/trust/` layout, version pins, `make` entry points and safe secret-handling approach; implement the minimum needed | Pending |
| 2 | KMS protocol and recovery decisions | Specify per-node wrapped key context, seal/unseal envelope, TLS endpoint and certificate handling, session authorization, early boot DNS/NTP, admission restrictions, and independent loss recovery | Pending |
| 3 | `ups-aux` KMS implementation | Service and Ansible configuration deployed; authorized `Seal`/`Unseal`, expiry, restart and fail-closed checks verified independently of Kubernetes/OpenBao | Pending |
| 4 | Pi 4 UEFI live-boot experiment | EDK2 card cold-boots; generic ARM64 Talos installer sees Ethernet, memory and explicitly identified disks; evidence recorded below | Pending |
| 5 | OS storage and machine configuration | Confirm supported bootable MD RAID1 path, immutable disk selectors, pre-`STATE` networking and KMS-backed `STATE`/`EPHEMERAL` settings; validate before destructive actions | Pending |
| 6 | Install encrypted Talos | Deliberately install onto assigned OS disks only; cold boot with the independent KMS authorized; encrypted volume coverage verified | Pending |
| 7 | Bootstrap Kubernetes | Bootstrap the single control-plane node; verify API, node readiness, system pods, DNS and Flannel networking | Pending |
| 8 | Recovery and repeatability | Verify KMS locked/unlocked cold boots, expiry and failure modes, OS mirror degraded boot/recovery, and documented reproducible rebuild | Pending |

**Milestone boundary:** Stage 7 is the first target. Do not expand into OpenBao, ZFS LocalPV, ingress, certificates, monitoring, backups or the dependent-cluster KMS adapter until the basic encrypted Trust cluster is working. Stage 8 validates that milestone's recovery characteristics before treating the installation as production-ready.

### Decisions to settle as we go

| Topic | Current direction / unresolved question |
| --- | --- |
| Cluster and node identity | `trust` / `trust-cp1` agreed; stable API endpoint agreed in [network.md](../network.md#kubernetes-api-endpoint), DNS resolution verified 2026-11-08 |
| Networking | VLAN 10, `10.10.0.10/24`, gateway `10.10.0.1`; current proposed pod/service CIDRs and Flannel are in [network.md](../network.md). Pre-`STATE` DNS and NTP details TBD |
| Provisioning | **Decided:** native single-document Talos patches organized by cluster/role/node are authoritative; commit a deterministic public multi-document per-node render and enforce regeneration through CI. No custom node schema. Full Talos generation + secret handling TBD |
| Versioning and upgrades | Agreed: explicit Talos, Kubernetes and kubectl version pins, with Kubernetes selected from the target Talos release's recommended/default Kubernetes version and kubectl chosen to match. `talosctl` matches Talos. Upgrade Talos first, verify health, then upgrade Kubernetes separately; check compatibility and supported upgrade paths before either action. Selected: Talos `v1.14.5`, Kubernetes `v1.37.1`, kubectl `v1.37.1`; talosctl follows Talos. Scoped Linux CLI acquisition, checksums and public-bundle validation implemented; hardware deployment unverified |
| Boot | First experiment is SD-first EDK2/UEFI plus generic ARM64 Talos installer; supported behavior and firmware boot dependency must be verified |
| Storage | Two explicitly assigned OS SSDs are intended for MD RAID1; confirm stable identities, Talos compatibility, metadata format, degraded boot and replacement before any destructive installation. Separate encrypted ZFS data disks are **out of scope and protected** |
| Encryption | KMS-backed `STATE` and `EPHEMERAL` on the **initial** installation. Talos bootloader/kernel still require readable boot components; no claim of fully encrypted boot media |
| KMS | Dedicated coordinator service on `ups-aux`, independent of Trust and OpenBao; YubiKey-authorized one-hour key window, TLS and encrypted wrapped records per [security policy](../security/security.md#trust-bootstrap-kms). Precise service and recovery contract TBD |
| Secret handling | Never write plaintext Talos machine secrets, talosconfig, kubeconfig, KMS keys or unsealed material to workstation disk. Final generation/transport/bootstrap workflow TBD |

### Version-selection and upgrade policy (agreed)

- The Talos release **drives** selection of the Kubernetes version for a cluster. Review the selected Talos release's default/recommended Kubernetes version and supported Kubernetes range; record the chosen compatible Kubernetes version explicitly rather than deriving it automatically at runtime.
- Record **explicit pins** for Talos, Kubernetes and `kubectl` in the Trust cluster scope. Keep `talosctl` at the selected Talos version and `kubectl` at the selected Kubernetes version (or an explicitly reviewed compatible patch release). The exact file schema and acquisition/checksum implementation are part of provisioning design.
- Do not update pins automatically when upstream releases appear. Changing a version in Git does not itself upgrade any running node or Kubernetes components.
- Normally perform the Talos and Kubernetes upgrades in the **same planned maintenance session**, as two separately verified operations: preflight supported version/upgrade paths and encryption/KMS recovery, upgrade Talos, verify node/Talos API and Kubernetes health, then run the supported Kubernetes upgrade procedure and verify final health. If the old Kubernetes version is incompatible with the target Talos version, plan an intermediate supported path rather than applying that order blindly.
- Treat Trust as a single-node cluster with expected workload/API downtime during reboot or control-plane maintenance. Record actual upgraded versions, health checks and recovery steps. Do not conflate `kubectl` client pinning with upgrading the Kubernetes control plane.

**Initial version selection:** Talos `v1.14.5`, Kubernetes `v1.37.1` (Talos 1.14.5 default), kubectl `v1.37.1`; talosctl follows `v1.14.5`. The committed `clusters/trust/versions.yaml` is a declaration, not proof of provisioned tooling or a deployed cluster. See [Talos v1.14.5 release](https://github.com/siderolabs/talos/releases/tag/v1.14.5) and [release constants](https://github.com/siderolabs/talos/blob/v1.14.5/pkg/machinery/constants/constants.go).

### Native configuration sources and committed render (Point 2)

**Decided:** `clusters/trust/talos/patches/` holds native Talos typed-document fragments, ordered cluster-wide → control-plane → node-specific. Each fragment owns a separate Talos document (no duplicate `apiVersion`/`kind`/`name`). The renderer deliberately assembles documents instead of reimplementing Talos strategic merge semantics. Add new fragments only when a supported Talos configuration field is needed.

`clusters/trust/talos/rendered/trust-cp1.yaml` is committed for inspection and historical review. It is generated, never hand-edited. `make -C clusters/trust render` updates it; `make -C clusters/trust check-rendered` verifies exact content in CI. The current output is a **partial non-secret patch bundle**, not a deployable MachineConfig: defaults, cluster PKI, KMS, disk configuration and other security-sensitive material will only be included when a complete config is produced in memory during the later secret-handling work. The two pipelines must use the **same source patches and order**. CI freshness/heuristic secret checks are not an attestation that an arbitrary YAML file contains no sensitive values.

Current authored documents specify pod/service CIDRs, hostname, and provisional static networking. Network interface identity and validity against pinned Talos still require live hardware and Talos-specific validation. See [Trust cluster README](../../clusters/trust/README.md).

### Talos secrets lifecycle (Point 3)

**Decision: generate once, recover consistently.** Trust's Talos machine
identity and cluster PKI are generated once using the pinned native
`talosctl gen secrets` command. Authenticate and wrap the result under
`homelab-wrap-v1` using the existing YubiKey-based library; persist only
the encrypted record in the private records submodule. Every subsequent
installation, repair, configuration render or rebuild must recover the
**same** bootstrap secret bundle. Missing, corrupt or mismatched records
are fatal: never silently generate replacement cluster credentials.

**Agreed recovery model:** `homelab/v1/trust/talos/bootstrap/r1` is the durable
Talos authority; reissue client credentials from that material rather than
maintaining a separate wrapped `talosconfig`. No production bootstrap bundle
has been created yet. Routine client lifetime is a 24-hour target under the
[administration policy](../security/security.md#trust-administration-credentials).
Kubernetes credential recovery/lifetimes remain undecided; see the
[YubiKey catalogue](../security/yubikey.md). Add only actually generated records
to the manifest. The independent coordinator KMS key is a separate secret.

**Configuration and delivery:**
1. Explicit one-time initialization, with operator intent and YubiKey touch,
   generates Talos secrets in a protected memory-only execution workspace,
   verifies authenticated wrapping, and creates ciphertext exclusively.
   Existing records must cause an error rather than being overwritten.
2. For every deployment, unwrap that same record after YubiKey authorization.
   Use pinned Talos config-generation and validation with the exact same
   native source patches used by the committed public render.
3. The committed public YAML stays a non-secret inspection bundle, not an
   apply-ready MachineConfig. The complete secret-bearing configuration,
   talosconfig and kubeconfig live only in the protected memory workspace.
4. Use explicit node targets and Talos-supported apply mechanisms to supply
   the complete configuration. Do not pass the public render directly to
   `talosctl apply-config`; never place plaintext in shell arguments,
   environment variables, logs, disk-backed temporary files or Git.
5. Rebuilds first verify independently accessible wrapped records, approved
   Talos version, and KMS recovery. Repeatable configuration generation must
   not rotate the identity.

**Implementation gates (not yet satisfied):** verify the exact Talos 1.14.5
secrets/config generation and validation CLI behavior; define the bundle
format, record filenames and admin credential recovery; establish a
private, size-limited RAM-backed workspace with checked mount type and
permissions, approved OS swap protection, no core dumps or insecure subprocess temporary
files or logging; and test create/recover/apply preparation using only
disposable secret material. If any safety prerequisite cannot be established,
fail closed. The later provisioning helper must verify no plaintext survives
outside process memory/RAM-backed storage on success or failure.

**Implemented initial helper:** `scripts/trust_talos_secrets.py` provides explicit `init` and pipe-only `recover` actions. It uses native `talosctl gen secrets --output-file -` and existing `homelab-wrap`/`homelab-unwrap` CLIs, requires exact absolute executable paths, rejects existing records and unprotected/unverified swap, hardens the process, and never writes plaintext files. It has mocked orchestration tests and disposable subprocess/Git regression tests; the disposable pinned-tool/YubiKey rehearsal passed on `simlun-x1` on 2026-11-07. Recovery bounds output and subprocess time and emits only after successful, nonempty unwrapping. The private-record path must be a tracked, initialized Git submodule. No admin credential generation, full machine configuration, Talos installation, or apply command is implemented. The direct-to-pipe flow means no memory-backed filesystem is required for *this helper*, but future native `gen config` consumption must still satisfy the memory-only workspace constraints. See
[security policy](../security/security.md#secret-handling-boundary),
[helper implementation](../security/helper-implementation.md), and
[wrapped-record storage](../security/encrypted-record-storage.md).

The disposable rehearsal is now implemented as
`make -C clusters/trust secrets-rehearse`; see the
[rehearsal instructions](../../clusters/trust/README.md#disposable-secret-rehearsal).
It uses an isolated ciphertext repository and a distinct wrapping context,
checks exact in-memory recovery plus overwrite/corruption/missing-record
failures, and leaves the production identity untouched. The operator's actual Talos/YubiKey rehearsal **passed** on `simlun-x1`
(Linux amd64) on 2026-11-07, with the implementation at `d7cf86b` and HSM pin
`c4430a3`: exact in-memory recovery, overwrite refusal, damaged-ciphertext
rejection, missing-record rejection and temporary-repository cleanup all passed.
No production Trust identity was created.

**Workstation swap finding (2026-11-07):** On `simlun-x1`, active swap is
`cryptoswap` on `/dev/nvme0n1p2`, with mapping UUID `CRYPT-PLAIN-cryptoswap` and
crypttab entry `cryptoswap /dev/nvme0n1p2 /dev/urandom swap,initramfs`.
The operator also verified `/etc/crypttab` as `root:root 664`. Group `root`
(GID 0) is trusted to write this configuration; non-root ownership, write access
by other groups, and world write access remain rejected. The guard correction
was merged through [HSM PR #10](https://github.com/simlun-ai/homelab-hsm/pull/10);
the parent code pin now uses the merged upstream main revision.
The operator's output supports random-key encrypted swap under normal boot
activation. Agreed to allow this under the shared
[workstation policy](../security/security.md#secret-handling-boundary), replacing
the blanket no-swap guard in Trust. No swap configuration was changed. The
updated runtime swap check passed during the successful workstation rehearsal.

### Scoped tooling and native validation (Point 4)

Implemented `tools`, `check-tools`, and `validate` alongside the existing render
commands. Release pins remain centralized; downloaded clients are cluster-local
and verified against reviewed upstream SHA-256 values. CI runs native strict
validation of the public bundle offline after tool acquisition. See the
[Trust operating instructions](../../clusters/trust/README.md#scoped-tools-and-validation).

On 2026-11-07, the operator verified `make -C clusters/trust tools` and
`make -C clusters/trust validate` on `simlun-x1` (Linux amd64), using the
Point 4 implementation from commit `ff42ab0`. Both pinned clients passed
checksum verification, the committed render matched its patches, and native
Talos validation passed for metal mode. Linux arm64 download metadata is provided but
execution on an arm64 workstation is not yet verified. This does not validate a
complete secret-bearing machine configuration or any physical installation.

### Full configuration and administration credential rehearsal

Implemented `make -C clusters/trust config-rehearse`, using disposable secrets,
the committed native patches and sealed anonymous memory descriptors. Native
Talos generation and strict validation pass on amd64; native client-info checks
also pass for fresh and reissued administration credentials from the same bundle.
CI repeats this preparation without network access. See the
[rehearsal contract](../../clusters/trust/README.md#offline-configuration-rehearsal).
The hostname patch now disables automatic hostname selection explicitly so it
can merge with Talos-generated defaults without conflict.

**Operator verification passed on 2026-11-08:** `simlun-x1` (Linux amd64),
commit `d12de94`, `make -C clusters/trust config-rehearse`. The operator reported
all checks passing: sealed anonymous descriptors, native strict metal-mode
validation of the generated configuration, rejection of invalid supplied secrets
without implicit regeneration, administration credential issuance/reissuance
from the same bundle, and descriptor cleanup without named plaintext files.
This establishes a disposable preparation path, not deployable Trust settings
or actual node access. The stable endpoint and Talos recovery/lifetime policy are now agreed;
production identity creation, issuance from recovered bootstrap material, KMS/disk
configuration, Kubernetes credential retrieval and apply operations remain gated. No additional wrapped administration record has
been created; native client reissuance from bootstrap material is demonstrated.

### Endpoint and administration decisions (2026-11-08)

The [network overview](../network.md#kubernetes-api-endpoint) owns the agreed
production API URL and direct-node DNS mapping. The operator configured and
verified DNS on 2026-11-08 via the gateway and workstation resolver;
the configuration rehearsal deliberately retains its `.invalid` endpoint.

The [security policy](../security/security.md#trust-administration-credentials)
owns the bootstrap-authority and 24-hour routine client decision. Pinned-source
inspection confirms offline native signing supports the target lifetime, while
`config new` needs a live node. The offline signing tools require named paths,
and the protected named-file workflow is now implemented in the separate
credential rehearsal below.
Native offline 24-hour CSR/signing was smoke-tested with fixed public dummy
CA/client keys; issuer signature, client key match, role, client-auth usage and
expiry passed. This is not verification of the protected-memory bootstrap
recovery workflow or node authentication. The existing configuration rehearsal
still exercises native one-year credentials. No production secrets were created by these checks. DNS was subsequently
configured and verified as recorded above.

### Protected 24-hour client issuer

Implemented `make -C clusters/trust credentials-rehearse`; see the
[workspace and rehearsal contract](../../clusters/trust/README.md#protected-24-hour-credential-rehearsal).
It uses a disposable native CA, issues a 24-hour client with native commands,
checks the certificate/key/role/expiry and inspects the assembled talosconfig.
Filesystem admission, cleanup, resource-limit and certificate-policy unit tests
pass; CI runs native issuance offline on a dedicated tmpfs mount.

**Operator verification passed on 2026-11-08:** `simlun-x1` (Linux amd64),
commit `bd1e759`, `make -C clusters/trust credentials-rehearse`, using `/dev/shm`.
All checks passed: issuer signature, client key match, `os:admin` role,
client-auth usage, 24-hour expiry, native talosconfig assembly/inspection and
RAM workspace cleanup. The scoped tools verified Talos `v1.14.5` and kubectl
`v1.37.1`. No production bootstrap bundle was generated or recovered.

The reusable issuer accepts existing CA PEM material. Extraction and integration
with a disposable wrapped Talos bundle are implemented in the recovery rehearsal
below; selected production endpoints and live-node authentication remain pending. The
previous `config-rehearse` target still tests native default one-year generation.

### Wrapped recovery and reissuance rehearsal

Implemented `make -C clusters/trust recovery-rehearse`; refresh the helper
environment first with `make -C support/hsm tools` for the pinned offline YAML
parser. See the [rehearsal contract](../../clusters/trust/README.md#wrapped-recovery-rehearsal).
The target wraps a disposable native bootstrap bundle and recovers it twice,
validates generated machine configurations against the public patches, and
issues fresh 24-hour clients from the recovered Talos authority. It checks
machine/client CA continuity, unchanged recovered input and ciphertext, and
fresh client keys/certificates. Temporary ciphertext Git fixtures and RAM
workspaces are removed on completion. CI uses real wrapping with a public fake
responder; workstation/YubiKey verification is pending. No production identity,
node authentication, installation or apply is performed.

### Step-by-step working rules

1. Choose **one** pending decision or test; document any preconditions before implementation.
2. Add only the files, commands and checks needed for that step; keep all affected documentation synchronized.
3. Record the relevant commit/revision, selected versions, host/disk identities, real observations and failure/recovery notes **without secret output**.
4. Check a milestone only when its exit criteria have been verified; leave unsuccessful experiments and revised decisions visible.
5. Before running any destructive storage operation, positively identify targets and explicitly exclude the separate Trust data mirror. Never infer a safe disk from `/dev/sdX`, size or apparent emptiness alone.
6. After the operator validates a step, ask whether this roadmap should be updated to record the result.

### Progress log

| Date | Milestone | Evidence / decision | Next action |
| --- | --- | --- | --- |
| 2026-11-06 | 0 — baseline | Started `feat/trust-bootstrap` after the Trust rename; accepted `trust-cp1` and `10.10.0.10`. `ups-aux` base setup previously verified. No Trust disk or KMS tests performed | Review provisioning layout and pinning strategy |
| 2026-11-06 | 1 — version policy | Agreed explicit Talos, Kubernetes and kubectl pins, with Talos driving Kubernetes selection; same-session Talos-first, Kubernetes-second upgrade policy with intermediate health checks | Select and record exact release pair |
| 2026-11-06 | 1 — initial pins | Selected Talos `v1.14.5` and its default Kubernetes `v1.37.1`, matched kubectl `v1.37.1`; declared versions, not installed or verified on Trust hardware | Design scoped tool acquisition and provisioning |
| 2026-11-06 | Point 2 — native patch design | Native layered Talos documents, committed public per-node bundle, CI reproducibility check; no installation or secret-bearing config generation | Point 3: secure generation and transport |
| 2026-11-06 | Point 3 — secret lifecycle design | Generate-once Talos identity with authenticated wrapped-record recovery; full machine config/admin clients remain memory-only. Implementation and testing pending | Implement the helper and recovery tests before operational apply |
| 2026-11-07 | Point 3 — bootstrap helper | Added guarded generate-once and pipe-only recovery helper plus mocked unit tests; no production secrets generated or hardware test executed | Test with disposable keys and pinned toolchain; implement protected config generation/admin access |
| 2026-11-07 | Point 4 — scoped tooling | Pinned Linux clients, reviewed hashes and native strict public-bundle validation implemented; amd64 acquisition/validation tested, no hardware changes | Disposable secret-helper tests and protected complete configuration/admin credential workflow |
| 2026-11-07 | Point 4 — operator verification | `simlun-x1`, Linux amd64: `make tools` verified talosctl `v1.14.5` and kubectl `v1.37.1`; `make validate` passed render freshness, client verification and native metal-mode validation. Point 4 complete; no node installation performed | Test the secret workflow with disposable material |
| 2026-11-07 | Point 3 — operator rehearsal | `simlun-x1`: `make secrets-rehearse` passed all checks with the physical YubiKey and approved encrypted swap; disposable repository removed, no production identity created | Complete protected machine configuration generation and admin credential recovery |
| 2026-11-08 | Configuration — operator rehearsal | `simlun-x1`, commit `d12de94`: `make config-rehearse` passed all checks; disposable material only, no node operations | Decide production API endpoint and client lifetime/renewal, then integrate secret recovery |
| 2026-11-08 | Trust API DNS — operator verification | Cloud Gateway Ultra DNS entry configured; `simlun-x1` resolved the required name through `dig @10.10.0.1` and `getent ahostsv4`; details in [network.md](../network.md#required-dns-entries) | Implement protected 24-hour Talos client issuance |
| 2026-11-08 | Credentials — operator rehearsal | `simlun-x1`, commit `bd1e759`: `make credentials-rehearse` passed native 24-hour issuance, certificate policy, talosconfig assembly/inspection and cleanup on `/dev/shm`; disposable CA only, no node operations | Integrate wrapped bootstrap recovery with protected generation and client issuance |

Review fixes (2026-11-07): enforce Trust render checks in `make ci`, include cluster Python in lint/type/syntax checks, verify the private Git submodule, and bound secret subprocess capture before releasing recovered bytes. Native public-bundle validation was subsequently implemented in Point 4.

---

**Installation in progress; hardware steps and KMS remain unverified until explicitly recorded below.**

Install the independent Trust cluster after the [main coordinator](01-main-coordinator.md) is ready. Firmware-card preparation can be tried separately while the coordinator/KMS work is pending.

Use `10.10.0.10/24` with gateway `10.10.0.1` on `k8s-aux` (VLAN 10) for the installed `trust-cp1` node (`trust-cp1.k8s-aux.lundmark.internal`). Plan for this address to be available before Talos loads encrypted `STATE`, so the node can reach the coordinator's KMS on `10.10.0.5`. The preboot configuration and KMS endpoint are still TBD. See the [network overview](../network.md) for the Trust load balancer pool and proposed Kubernetes CIDRs.

## First installation experiment: Pi 4 UEFI

The first method to try is [pftf/RPi4](https://github.com/pftf/RPi4) firmware on a dedicated microSD card, booting a generic Talos ARM64 installer from USB and installing onto the assigned OS SSD mirror. This is a candidate installation method, not a settled design or a verified supported combination.

The SD card remains inserted for normal operation and is a boot dependency outside the SSD mirror. Keep all disk operations below confined to the firmware card; the [Trust data disks](../inventory.md#trust) are not installation targets.

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

## Later platform and service milestones

- [ ] Validate Talos installation, boot, MD RAID1, and KMS encryption on the assigned OS disks; implement the pinned tooling and Trust bootstrap configuration.
- [ ] Document manual encrypted ZFS mirror preparation and deploy the planned platform services and OpenBao, including workstation/YubiKey unseal support.
- [ ] Verify cold startup, scheduled Raft snapshot backups, and the required restore paths; record results and update the recovery guide.

References: [Trust architecture](../clusters.md#trust), [hardware and disks](../inventory.md#trust), [repository layout](../layout.md#common-cluster-layout), [OpenBao unseal](../security/openbao-unseal.md), [backup and recovery](../backup-and-restore.md).
