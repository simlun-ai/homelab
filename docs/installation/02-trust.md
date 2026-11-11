# 02 - Trust

## Working roadmap: encrypted Talos and Kubernetes bootstrap

**Primary milestone:** Install `trust-cp1` as an encrypted Talos single-node Kubernetes cluster on `k8s-aux` (VLAN 10), with system-volume unlock provided by the independent KMS on `ups-aux`. This is the initial installation, **not** a disposable unencrypted bootstrap. OpenBao and other application workloads are later milestones.

**Working branch:** `feat/trust-bootstrap`. Work in small, reviewable commits on this branch. Before each change, agree on the next decision, implement only that slice, test it where possible, and update this roadmap with evidence. Do not mark physical tests complete from configuration or documentation alone.

### Current position

- **Completed prerequisite:** `ups-aux` base bootstrap/hardening and console login verified (2026-11-06). Its additional KMS service is staged and verified locked; production TLS and live-node authorization remain pending.
- **Decided identity:** cluster `trust`, control-plane node `trust-cp1`, FQDN `trust-cp1.k8s-aux.lundmark.internal`, static IP `10.10.0.10/24`; coordinator `ups-aux` at `10.10.0.5`.
- **Verified firmware boot:** SD-first EEPROM configuration and first UEFI setup boot passed on 2026-11-08. On 2026-11-09 the operator confirmed UEFI Firmware v1.53 and returned to setup after a full power cycle without changing settings. Talos subsequently reached maintenance mode via manual USB selection on 2026-11-09. Disabling the 3 GB RAM cap and cold booting subsequently yielded memory TOTAL `7748` with unchanged UUID and working Ethernet. EEPROM version/exact BOOT_ORDER, other modified settings and automatic USB selection remain unverified.
- **Planned, not verified:** Talos installation, MD RAID1 for the OS disks, KMS-backed `STATE`/`EPHEMERAL` encryption, and Kubernetes bootstrap.
- **Current next step:** Validate [production certificate initialization and recovery](trust-kms-cloudflare.md#production-certificate-provisioning-and-recovery) on `ups-aux`. The implementation separates staging/production state and wrapping contexts, checks production trust, and renews production only when due; installation and live validation are pending. The [coordinator-local staging lifecycle](trust-kms-cloudflare.md#wrapped-staging-state-initialize-recover-and-recreate) passed on 2026-11-11: import, recovery/renewal, explicit recreation and recovery/renewal of the replacement, with reported local archival. Production renewal and the locked TLS listener follow. The [Certbot staging rehearsal](trust-kms-cloudflare.md#run-the-staging-rehearsal) passed: issuance, renewal with the same TLS key, workspace removal and the post-run public DNS check. The operator verified the local service starts locked with the [dedicated staging play](01-main-coordinator.md#stage-the-locked-service). The Pi's network-only rehearsal confirmed the planned static address, route and DNS, followed by DHCP rollback. The KMS TCP probe timed out. The corrected `enabcm6e4ei0` LinkConfig passed offline validation on the operator workstation. The standalone MD RAID1 draft passed strict offline validation with pinned `talosctl`. The maintenance-mode volume probe confirmed that both appear as whole disks. All four ATA device links and exact capacities matched after a cold boot. The full-memory cold boot passed with unchanged UUID and Ethernet. UEFI v1.53 and the manual Boot Manager USB path have reached Talos maintenance mode. KMS software-core and loopback gRPC-over-TLS tests passed on the workstation. The operator also verified the local authorization socket, worker lifecycle and late-response rejection. Coordinator TCP/TLS deployment, production identity creation and live-node authentication remain pending. Disk/adapter behavior and actual pre-STATE/KMS networking, DNS and time remain to be verified on the Pi before installation.

Trust's four 128 GB SSDs have [planned mirror assignments](../inventory.md#mirror-assignments). Use the
`/dev/disk/by-id/ata-*` links in the
[candidate disk inventory](../inventory.md#candidate-disk-inventory) to identify
the physical SSDs. Each link includes the SSD's ATA serial and matched on the
workstation and the Pi. The Pi also reported USB-side links and the same WWID
for all four SSDs. A cold boot confirmed that the ATA links and exact
capacities matched the first discovery. Validate the Talos disk-selection
mechanism separately before installation.

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
production certificates, scheduled renewal and the TCP/TLS listener remain
pending. See [step 01](01-main-coordinator.md#prepare-cloudflare-and-rehearse-acme)
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
Production issuance, scheduled renewal and the TLS listener remain pending.

### Production certificate attempt (2026-11-11)

The tools play passed on `ups-aux` (`ok=11`, `changed=3`, no unreachable hosts or
failures). Production initialization reported issuance starting, then failed
before wrapping/publication. Native Certbot 4.0.0 reproduction identified a
renewal-file parsing defect: top-level lineage metadata was not accepted by
the original INI check. The fix accepts the native layout and adds safe
stage-specific failure diagnostics. Reinstall the corrected helper and retry
according to the [production guide](trust-kms-cloudflare.md#production-certificate-provisioning-and-recovery).
Production initialization/recovery acceptance remains pending. Issuance may have
completed before the failed check; do not repeatedly retry against production.

### Milestone tracker

| # | Stage | Exit criteria | Status |
| --- | --- | --- | --- |
| 0 | Identity and working baseline | Names/IP/roles and owning files agree; branch and roadmap established | In progress — baseline recorded; branch created |
| 1 | Provisioning contract and scoped tools | Agree on declarative node/disk schema, `clusters/trust/` layout, version pins, `make` entry points and safe secret-handling approach; implement the minimum needed | Pending |
| 2 | KMS protocol and recovery decisions | Specify per-node wrapped key context, seal/unseal envelope, TLS endpoint and certificate handling, session authorization, early boot DNS/NTP, admission restrictions, and independent loss recovery | Payload/session behavior, endpoint and sequence approved; wire details proposed; UUID/time/admission/recovery choices pending |
| 3 | `ups-aux` KMS implementation | Service and Ansible configuration deployed; authorized `Seal`/`Unseal`, expiry, restart and fail-closed checks verified independently of Kubernetes/OpenBao | Pending |
| 4 | Pi 4 UEFI live-boot experiment | EDK2 card cold-boots; generic ARM64 Talos installer sees Ethernet, memory and explicitly identified disks; evidence recorded below | In progress — UEFI/Talos maintenance boot, full memory and UUID/link continuity across the RAM-cap cold boot verified; all four candidate SSDs detected on the Pi with matching ATA links and capacities across a cold boot |
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
| Storage | Two explicitly assigned OS disks are intended for MD RAID1; confirm stable identities, Talos compatibility, metadata format, degraded boot and replacement before any destructive installation. Separate encrypted ZFS data disks are **out of scope and protected** |
| Encryption | KMS-backed `STATE` and `EPHEMERAL` on the **initial** installation. Talos bootloader/kernel still require readable boot components; no claim of fully encrypted boot media |
| KMS | Dedicated coordinator service on `ups-aux`, independent of Trust and OpenBao; YubiKey-authorized one-hour key window, TLS and encrypted wrapped records per [security policy](../security/security.md#trust-bootstrap-kms). See the [draft service contract](../security/trust-bootstrap-kms.md); review and independent recovery details pending |
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
responder; the native CI rehearsal passed. No production identity,
node authentication, installation or apply is performed.

**Operator verification passed on 2026-11-08:** `simlun-x1` (Linux amd64),
`make -C clusters/trust recovery-rehearse`, using the physical YubiKey and
`/dev/shm`. The pinned clients and public render checks passed. Both recoveries
passed native strict metal-mode machine validation and authority continuity;
fresh 24-hour clients passed certificate policy and native talosconfig inspection.
The final checks confirmed reissuance from the same authority and removal of
the temporary ciphertext repository and RAM workspaces.

### Operating entry points (Point 5)

Agreed separate workflows: initialize the wrapped identity once; install a node
from the recovered authority after KMS/disk readiness; administer using fresh
24-hour clients recovered from that same authority. Installation and routine
administration must never generate a replacement identity. Installation
preparation and explicit apply remain separate; no apply workflow is implemented.

The first administration slice is implemented as `admin-inspect`, which requires
an existing production record and performs local inspection only. Its disposable
`admin-rehearse` counterpart exercises the same path with the physical YubiKey
without creating a production identity. Native CI uses the public fake responder;
the operator also verified the disposable path as recorded below. The wrapper uses context `trust` and derives
the direct Talos node/endpoint from the committed node address; it prints only
public metadata. See the [command contract](../../clusters/trust/README.md#administration-client-inspection).
Live Talos command delivery and authentication remain pending.

**Operator verification passed on 2026-11-08:** `simlun-x1` (Linux amd64),
`make -C clusters/trust admin-rehearse`, with the physical YubiKey and `/dev/shm`.
Pinned-client and render checks passed. Native signing and certificate policy
checks succeeded; local inspection reported context `trust`, endpoint and node
`10.10.0.10`, role `os:admin`, and expiry date `2026-11-09`. The final checks
confirmed removal of protected workspaces and disposable ciphertext. No
production record was created or used, and no node was contacted.

### Coordinator KMS contract draft

The [draft contract](../security/trust-bootstrap-kms.md) distinguishes existing
approved decisions from proposed wire formats, authorization/session behavior,
TLS/admission rules and independent recovery gates. Source inspection against
Talos `v1.14.5` and `kms-client v0.2.0` confirms the RPC shape, 32-byte unlock
input, ten-second operation timeout and explicit TLS endpoint requirement.
It does not verify stock-image boot behavior, Pi UUID stability, networking,
clock synchronization or recovery. Review the proposed envelope, local protocol and process model; require fixed
public cryptographic vectors as part of the disposable test harness.
No production keys, manifest entries, endpoint configuration or service were
created. Acceptance criteria are recorded; all service/hardware checks remain
pending.

### KMS walkthrough agreement (2026-11-08)

Approved the five-point [implementation sequence](../security/trust-bootstrap-kms.md#walkthrough-decisions-2026-11-08):
payload/session behavior, dedicated TLS endpoint, software-only tests,
non-destructive Pi discovery/connectivity, then staged coordinator deployment
and replacement recovery. In particular, a replacement authorization window
requires explicit lock and fresh touch; traffic never extends the hour, and
late results are discarded. The endpoint selection is recorded in
[network.md](../network.md#required-dns-entries) as pending configuration.
No live test, deployment or production key generation is established by this
agreement. Independent recovery copies/locations must be agreed before
production KMS key creation.

### KMS software core

Implemented `scripts/homelab/trust_kms/` with the exact bounded envelope format,
fixed public HKDF/AES-GCM vector and a controlled-clock session model. Parent
helper tests cover round trips, tampering/malformed input, explicit generation
selection, atomic activation, acknowledgment recovery, expiry/lock/restart,
bounded admission and stale in-flight results. Existing helper CI discovery runs
these software tests without hardware or network calls. See the
[implementation limits](../security/trust-bootstrap-kms.md#implemented-software-core-and-its-limits):
this record covers the original in-process core. See the
[daemon rehearsal](../security/trust-bootstrap-kms.md#disposable-loopback-transport)
for the subsequent worker, local authorization and TLS implementation.

**Operator verification passed on 2026-11-08:** `simlun-x1`,
`make -C support/hsm test`, following the KMS core implementation at `8a5d8f9`.
The target completed successfully: its parent suite runs before the component
suite, whose final summary reported 74 tests in 0.195 seconds, `OK`. This records
software-test validation only; it does not establish daemon, transport, physical
YubiKey session authorization, Pi boot or disk-unlock verification.

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
| 2026-11-08 | Wrapped recovery — operator rehearsal | `simlun-x1`: `make recovery-rehearse` passed with the physical YubiKey and `/dev/shm`; both recovered bundles produced validated machine configurations and fresh 24-hour clients under the same authority; temporary ciphertext and RAM workspaces removed | Settle initial-installation versus ongoing-operation entry points (Point 5) |
| 2026-11-08 | Administration — operator rehearsal | `simlun-x1`: `make admin-rehearse` passed with the physical YubiKey and `/dev/shm`; native 24-hour client issuance, context/target/role inspection and cleanup verified; disposable identity only | Review remaining installation prerequisites and select the next slice |
| 2026-11-08 | KMS contract — documentation draft | Pinned Talos/proto source inspected; proposed envelope, authorization, failure/recovery behavior and test gates documented; no implementation or deployment | Review contract and resolve open choices before disposable service tests |
| 2026-11-08 | KMS — software core | Envelope/session logic and independent public vector implemented; controlled-clock and race tests pass locally; no service or hardware operations | Review core evidence; proceed with Pi discovery and remaining service integration gates |
| 2026-11-08 | KMS core — operator software tests | `simlun-x1`: `make -C support/hsm test` completed successfully; parent suite followed by the HSM component suite (74 tests, `OK`); no hardware/service operations | Proceed with non-destructive Pi discovery; daemon/transport and deployment gates remain pending |
| 2026-11-08 | Pi firmware — operator verification | SD-first EEPROM step completed; separate firmware microSD card reached UEFI setup; exact EEPROM/UEFI display versions and BOOT_ORDER not captured | Confirm cold-boot settings persistence, then prepare the separately identified Talos ISO USB medium |
| 2026-11-09 | Pi UEFI — cold-boot verification | Operator confirmed UEFI Firmware v1.53 and returned to setup after a full power cycle; settings were unchanged, so modified-setting persistence is not established | Identify and prepare the separate Talos ISO USB medium; keep candidate disks disconnected |
| 2026-11-09 | Talos live boot — operator verification | Manually selected USB installer in UEFI Boot Manager; reached maintenance mode at DHCP `10.10.0.246`; automatic USB selection and hardware/API inspection not yet verified | Run read-only UUID, network, memory and time discovery; preserve discovery-only scope |
| 2026-11-09 | Pi live baseline — operator verification | Scoped read-only queries confirmed Talos v1.14.5 ARM64, observed UUID, Ethernet/MAC at 1 Gbit/s, limited RAM and synchronized time; provisional `eth0` mismatch identified | Disable RAM limit and cold boot; repeat UUID/link/memory/time queries; correct network patch before any apply |
| 2026-11-09 | Pi full-memory cold boot — operator verification | Disabled UEFI RAM cap; TOTAL increased to `7748`; UUID, physical interface/MAC, 1 Gbit/s link and synchronized time retained at DHCP `10.10.0.246` | Inventory disks/adapters read-only; resolve `eth0` mismatch before any apply |
| 2026-11-09 | Trust disks — workstation inspection | Four candidate SATA SSDs inventoried with ATA serials and device links. Intenso showed a DOS/MBR signature. No partitions or mountpoints were listed | Identify adapters, verify Pi detection and finalize disk assignments |
| 2026-11-09 | Trust disks — Pi discovery | Maintenance-mode Talos detected all four 128 GB SSDs simultaneously through the powered hub. Each ATA link matched the workstation, and all four shared WWID `naa.5000000000000001`. The UEFI card and installer were identified separately in the [live disk inventory](../inventory.md#live-talos-disk-inventory) | Recheck ATA links after a cold boot and choose the OS/data pairs |
| 2026-11-09 | Trust disks — cold-boot recheck | All four ATA links matched the initial Pi discovery and each SSD again reported 128,035,676,160 bytes. The Patriot moved from `/dev/sdd` to `/dev/sdc` and the USB installer from `/dev/sdc` to `/dev/sdd` | Choose and record the OS and data mirror members by ATA link |
| 2026-11-09 | Trust disks — Talos volume probe | Read-only `get discoveredvolumes` reported both assigned OS SSDs as whole disks with 128,035,676,160 bytes each. No named filesystem or partition entries were reported for either. The USB installer was identified separately as ISO9660 with label `TALOS_V1_14_5` | Draft the exact ATA member selector and validate the RAID configuration offline |
| 2026-11-09 | Trust OS RAID1 — operator offline validation | On `simlun-x1`, pinned `talosctl` v1.14.5 accepted the [standalone RAID1 draft](../../clusters/trust/talos/experiments/trust-cp1-raid1.yaml) from `4b44036` with `validate --mode metal --strict`. The draft selects the two assigned OS SSDs by exact ATA link and targets the resulting MD array. | Correct and validate the Pi network patch. Array creation, boot and replacement still require live tests. |
| 2026-11-09 | Trust networking — operator offline validation | On `simlun-x1` at `1bd3ad9`, `make -C clusters/trust validate` confirmed the public render matched its source patches, verified the pinned clients and passed native strict metal-mode validation. LinkConfig targets `enabcm6e4ei0`. | Check the KMS DNS record and prepare a live network-only rehearsal. |
| 2026-11-09 | Trust KMS DNS — operator verification | From `simlun-x1`, `dig @10.10.0.1 kms.k8s-aux.simlun.se A +short` returned `10.10.0.5`. See [required DNS entries](../network.md#required-dns-entries). | Rehearse static networking on the Pi and check DNS from the node. |
| 2026-11-09 | Trust networking — live rehearsal | Talos accepted the network-only config in five-minute try mode. The Pi answered at `10.10.0.10/24` on `enabcm6e4ei0`, with the default route and DNS resolver at `10.10.0.1`. The KMS hostname resolved to `10.10.0.5` on the Pi, but TCP 443 timed out. The operator confirmed DHCP returned after rollback. | Implement and exercise the coordinator listener and transport, then repeat the Pi probe. |
| 2026-11-09 | Trust KMS — operator loopback TLS rehearsal | On `simlun-x1` at `b2ca4e6`, `make -C support/hsm kms-tls-rehearse` passed on Python 3.13.18 (`Ran 1 test`, `OK`). The untrusted client produced the expected self-signed certificate verification error. | Implement the local authorization socket, expiry scheduler and isolated key worker before coordinator deployment. |
| 2026-11-09 | Trust KMS — operator daemon rehearsal | On `simlun-x1`, `make -C support/hsm kms-tls-rehearse` passed all three tests (`Ran 3 tests`, `OK`). The run covered Unix socket authorization, worker lock, expiry and exit, rejection of a late response, and the TLS Seal/Unseal round trip. The untrusted-certificate rejection was expected. | Prepare coordinator service packaging and locked startup. |
| 2026-11-09 | Trust KMS — locked staging on `ups-aux` | `make -C support/ups kms-stage HOST=ups-aux` finished with `ok=14`, `changed=8`, `unreachable=0`, `failed=0`. The play verified the installed systemd unit and clean locked Unix-socket status. Enabling the UniFi device's **Local DNS Record** restored the coordinator SSH hostname. | Design and stage certificate issuance and the locked TLS listener. |

Review fixes (2026-11-07): enforce Trust render checks in `make ci`, include cluster Python in lint/type/syntax checks, verify the private Git submodule, and bound secret subprocess capture before releasing recovered bytes. Native public-bundle validation was subsequently implemented in Point 4.

---

**Installation in progress; hardware steps and KMS remain unverified until explicitly recorded below.**

Install the independent Trust cluster after the [main coordinator](01-main-coordinator.md) is ready. Firmware-card preparation can be tried separately while the coordinator/KMS work is pending.

Use `10.10.0.10/24` with gateway `10.10.0.1` on `k8s-aux` (VLAN 10) for the installed `trust-cp1` node (`trust-cp1.k8s-aux.lundmark.internal`). Plan for this address to be available before Talos loads encrypted `STATE`, so the node can reach the coordinator's KMS on `10.10.0.5`. The KMS endpoint is selected as `https://kms.k8s-aux.simlun.se:443`; preboot configuration and endpoint deployment/verification remain pending. See the [network overview](../network.md) for the Trust load balancer pool and proposed Kubernetes CIDRs.

## First installation experiment: Pi 4 UEFI

The first method to try is [pftf/RPi4](https://github.com/pftf/RPi4) firmware on a dedicated microSD card, booting a generic Talos ARM64 installer from USB and installing onto the assigned OS disk mirror. This is a candidate installation method, not a settled design or a verified supported combination.

The SD card remains inserted for normal operation and is a boot dependency outside the disk mirror. Keep all disk operations below confined to the firmware card; the [Trust data disks](../inventory.md#trust) are not installation targets.

This experiment aims to avoid the modified raw-image/META deletion and manual firmware-copy workaround described in [Talos issue #14555](https://github.com/siderolabs/talos/issues/14555#issuecomment-6464577848). Successful UEFI boot reports exist, but do not establish that our ISO installation, RAID1 failover, upgrades, or KMS unlock work.

### Discovery scope and boot artifacts

Begin with all candidate OS/data disks disconnected. Use a dedicated microSD
card for UEFI and a separate disposable USB stick for the Talos ISO. Neither
medium is a selected OS/data disk. Identify each by model, serial and capacity
before writing it; do not infer a device from `/dev/sdX` ordering. Firmware-card
formatting below deliberately erases only the positively identified card.

| Artifact | Selected release | SHA-256 |
| --- | --- | --- |
| `RPi4_UEFI_Firmware_v1.53.zip` | pftf/RPi4 `v1.53` | `ca9973e2a7a546b3df871cfb7382e656829114b6dfa424f40dc67cc90a217d88` |
| `metal-arm64.iso` | Talos `v1.14.5`, from `clusters/trust/versions.yaml` | `1b1d3b3d49d326da941cab967ffb92e927fa11c2893f5e5da8224dff255306cc` |

Release metadata was rechecked on 2026-11-08. This pins the generic ARM64 ISO,
without a Raspberry Pi overlay, custom schematic or machine configuration.
Keep the ISO hash synchronized with a deliberate Talos pin change. This is an
experiment, not evidence of Raspberry Pi compatibility or a supported mirror
installation method.

The [Talos ISO guide](https://docs.siderolabs.com/talos/v1.14/platform-specific-installations/bare-metal-platforms/iso)
states that applying machine configuration initiates installation, and that an
existing Talos installation on an attached disk can be used when booting an ISO.
Do not apply configuration during discovery. Before later attaching candidate
disks, inventory existing partition/filesystem signatures read-only on the
workstation; an existing Talos system must be reviewed before allowing the Pi
to boot with it attached. Do not erase it merely to obtain maintenance mode.
See the [mirror assignments](../inventory.md#mirror-assignments) for the selected OS and data disks.

First gate: reach UEFI setup with disks disconnected. Second gate: prepare the
separate ISO USB medium, then boot it into maintenance mode with candidate disks
still disconnected. Later discovery will record UUID stability across cold boots,
Ethernet/MAC, networking/DNS/time and disk/adapter identities in inventory.md.
A live network check does not prove pre-STATE networking or KMS unlock readiness.
No production identity creation, apply, formatting of OS/data disks or cluster
bootstrap belongs to these discovery gates.

### Prepare SD-first EEPROM boot

The Pi EEPROM bootloader must select SD before USB so that EDK2 runs before the disk bootloader. EEPROM boot order and EDK2's subsequent OS boot order are separate settings.

If SD-first boot is already configured, skip this step. Otherwise, on the workstation, use Raspberry Pi Imager with a spare card:

1. Select Raspberry Pi 4, then **Misc utility images → Bootloader → SD Card Boot**.
2. Write the recovery card.
3. Power off the Pi, disconnect USB disks, insert the recovery card, and power on.
4. Wait for a green HDMI screen and a steadily flashing activity LED.
5. Power off and remove the card.

This resets the EEPROM bootloader configuration. The recovery card may then be reformatted for UEFI below. See the [Raspberry Pi bootloader recovery instructions](https://www.raspberrypi.com/documentation/computers/raspberry-pi.html#reflash-the-bootloader).

### Download firmware on the Linux workstation

Use the release ZIP, not GitHub's source archive. Version 1.53 remains the
experiment pin. From the repository root, create an ignored working directory;
run the remaining download/card-preparation blocks from that directory:

```bash
mkdir -p clusters/trust/boot
cd clusters/trust/boot
```

```bash
curl -fL -o RPi4_UEFI_Firmware_v1.53.zip \
  https://github.com/pftf/RPi4/releases/download/v1.53/RPi4_UEFI_Firmware_v1.53.zip

echo 'ca9973e2a7a546b3df871cfb7382e656829114b6dfa424f40dc67cc90a217d88  RPi4_UEFI_Firmware_v1.53.zip' \
  | sha256sum --check
```

The checksum comes from the [release asset metadata](https://api.github.com/repos/pftf/RPi4/releases/tags/v1.53) rechecked on 2026-11-08; proceed only if verification succeeds.

### Download the Talos discovery ISO

From the same `clusters/trust/boot` directory, read the central Talos pin without
probing an installed CLI, then download the generic ARM64 ISO:

```bash
talos_release=$(python3 -I -B -c 'import runpy; print(runpy.run_path("../tooling.py")["version"]("talos"))')
curl -fL -o metal-arm64.iso \
  "https://github.com/siderolabs/talos/releases/download/${talos_release}/metal-arm64.iso"

echo '1b1d3b3d49d326da941cab967ffb92e927fa11c2893f5e5da8224dff255306cc  metal-arm64.iso' \
  | sha256sum --check
```

The hash is from the [Talos release asset metadata](https://api.github.com/repos/siderolabs/talos/releases/tags/v1.14.5).
Stop on any error. These commands download files only; writing the ISO to a
separate USB stick is a later step after that device is positively identified.
The ZIP must be extracted onto the FAT firmware card; it must not be flashed
as an image. The ISO uses a separate installer medium.

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
5. If the defaults are unchanged, no settings need saving. Power off fully, power on, and press **Esc** to confirm UEFI setup opens again. If making a deliberate change, save it and verify that setting separately after a cold boot.

After the first successful Talos boot, disable **Limit RAM to 3 GB**, reboot, and verify full memory availability plus working Ethernet and USB storage. The default limit addresses Pi DMA constraints; see [pftf's compatibility notes](https://github.com/pftf/RPi4#initial-notice).

The firmware card is ready once UEFI setup works. Keep it inserted. The next
experiment is to write the checksum-verified generic ARM64 ISO to the separately
identified USB installer and boot with candidate disks disconnected. Exact USB
device selection/write commands will be confirmed at that gate. RAID selectors
and installation commands remain TODO. After a future installation, prefer disk
boot entries over network boot entries in EDK2.

Artifact preparation (2026-11-08): both pinned downloads were retrieved and
SHA-256 verified in the development workspace; firmware ZIP inspection confirmed
`RPI_EFI.fd`, `config.txt`, `start4.elf` and `fixup4.dat` at its root. The central
Talos-pin lookup command was also checked. No card was written or Pi booted by
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
effect. TLS, KMS authentication and encrypted STATE unlock remain pending.
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
- [ ] Installed Talos cold boots with installation media removed.
- [ ] Cold boot succeeds with either OS disk disconnected, tested separately after restoring mirror health between tests.
- [ ] Rehearse replacing one OS SSD. Boot from the surviving member, verify the replacement's ATA link and size, update only the RAID member selector, then verify a two-member array, completed resync and boot from the replacement. Talos reconciliation adds matches. Removing the old link alone does not remove a member.
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

## Later platform and service milestones

- [ ] Validate Talos installation, boot, MD RAID1, and KMS encryption on the assigned OS disks; implement the pinned tooling and Trust bootstrap configuration.
- [ ] Document manual encrypted ZFS mirror preparation and deploy the planned platform services and OpenBao, including workstation/YubiKey unseal support.
- [ ] Verify cold startup, scheduled Raft snapshot backups, and the required restore paths; record results and update the recovery guide.

References: [Trust architecture](../clusters.md#trust), [hardware and disks](../inventory.md#trust), [repository layout](../layout.md#common-cluster-layout), [OpenBao unseal](../security/openbao-unseal.md), [backup and recovery](../backup-and-restore.md).
