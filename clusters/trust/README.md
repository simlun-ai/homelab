# Trust cluster

Independent foundational Kubernetes cluster, initially a single control-plane
node (`trust-cp1`, `10.10.0.10`). See the
[installation roadmap](../../docs/installation/02-trust.md).

## Scoped tools and validation

Requires Linux amd64 or arm64, GNU Make, Python 3.13–3.14, CA certificates,
and HTTPS access to GitHub releases and `dl.k8s.io` for initial acquisition.
Tools follow the **operator** architecture, independently of the Pi node.

```sh
make -C clusters/trust tools
make -C clusters/trust validate
```

`versions.yaml` owns release pins; `toolchain.toml` owns official download URL
patterns and reviewed SHA-256 values. The TOML format uses Python's standard
library, without a bootstrap package installation. When upgrading, deliberately
update pins and corresponding upstream hashes together; nothing selects latest
releases automatically. talosctl follows the Talos pin; kubectl follows its own pin.

`tools` verifies existing binaries and replaces missing or changed ones using
an atomic, checksum-verified download into ignored `bin/`. A failed download
leaves any previous binary untouched. A source-URL receipt prevents reusing an
old cached release after a pin change. `check-tools` verifies offline; it never
falls back to host binaries. `validate` requires verified tools and a fresh
public render, then runs native `talosctl validate --mode metal --strict`.
Both clients are hash-checked; no per-helper CLI version probing is required.
Tool acquisition prints flushed progress messages to stderr before cache checks,
downloads, checksum verification, installation and cleanup. Cache misses explain
why a download is needed; network failures identify the tool and source URL.

CI acquires tools in a preparation stage and runs the same validation without
network access. This validates only the authored public documents. Complete
machine configuration validation, KMS, disk selection and physical networking
remain later gates; passing this check does not make the bundle apply-ready.

## Native Talos patches and committed public render

Source fragments live in `talos/patches/`: cluster-wide documents, optional
control-plane documents, and `nodes/trust-cp1/`. Each file owns **one distinct
native Talos configuration document** (`apiVersion`, `kind`, optional `name`).
We do not maintain a second node inventory schema or implement Talos patch
merging ourselves.

```sh
make -C clusters/trust render
make -C clusters/trust check-rendered
```

Commit the regenerated `talos/rendered/trust-cp1.yaml` with its source patch
edits. CI byte-compares the regenerated output and rejects duplicate document
identities and common secret-bearing fields. This is a defense-in-depth guard,
not a substitute for reviewing content before committing it.

**The rendered bundle is deliberately NOT apply-ready.** It contains exactly
the authored public documents (without Talos-generated defaults, PKI, secrets,
installation disks, early boot configuration or KMS). Later, pinned Talos
tooling will build the complete native machine config using the same patches
and independently recoverable secrets **in memory only**, and validate before
applying. Never commit or persist that complete config on workstation disk.

The [Talos secret lifecycle](../../docs/installation/02-trust.md#talos-secrets-lifecycle-point-3) requires one-time native Talos generation, authenticated YubiKey wrapping and stable recovery of the same cluster identity. An experimental bootstrap-secret helper exists below; disposable administration credential recovery is verified below; production delivery and deployment remain unimplemented.

The Raspberry Pi `eth0` interface name and Talos behavior under UEFI remain
unverified. The operator reached UEFI setup on 2026-11-08 and confirmed UEFI
Firmware v1.53 with a successful repeat cold boot on 2026-11-09. Settings were
unchanged; modified-setting persistence and Talos ISO boot remain unverified.
Do not apply this partial public bundle to a node.

## Experimental bootstrap-secret CLI (Point 3)

`scripts/trust_talos_secrets.py` implements production `init`/`recover` and an
isolated `rehearse` action. This
script is **not** wired into production Make targets and does not apply Talos
configurations. The operator must provide absolute paths to `talosctl` and the installed
`homelab-wrap` or `homelab-unwrap` from the pinned HSM environment.
The requested Talos target version comes from `clusters/trust/versions.yaml`;
the helper does not check the CLI version (the scoped toolchain owns that). No ambient PATH fallback is accepted.

The private `secrets/wrapped/` path must be a tracked, initialized Git submodule
(symlinked paths are rejected). Every active swap area must satisfy the
[workstation swap policy](../../docs/security/security.md#secret-handling-boundary).
The helper disables core dumps, makes its own process non-dumpable, and
suppresses subprocess error output.
Initialize **once**, on a workstation with a YubiKey and already verified
tooling (commands shown with illustrative executable locations):

```sh
python3 -I -B scripts/trust_talos_secrets.py init \
  --talosctl /absolute/pinned/talosctl \
  --wrap /absolute/hsm/bin/homelab-wrap
```

It uses native `talosctl gen secrets --output-file -`, pipes plaintext
directly to `homelab-wrap --stdin`, and exclusively creates the ciphertext
record `secrets/wrapped/trust-talos-bootstrap.json`. The wrapper verifies the
encrypted record. Commit **only the encrypted record** to the private
submodule, and register its public metadata in `secrets/manifest.json`
after local generation/verification. The script refuses an existing record.

Recovery requires a downstream pipe/socket; **never use tee, redirection to
a regular file, command substitution, logging, or terminal output**.
Recovery buffers at most 1 MiB in memory and emits only after a successful,
nonempty unwrap, with a 180-second subprocess deadline. A future provisioning
consumer will take this stream directly into a protected native Talos generation
workflow. The current helper deliberately
does not offer an apply target.

Security limitations: ordinary workstation process memory is not physically
zeroizable through Python, and swap checks alone do not prove absence of all
OS dump mechanisms or instrumentation. Do not treat this as independently
audited protection. Initial generation/recovery must be exercised using
disposable secrets before the first real credential is created.

## Disposable secret rehearsal

After installing the [HSM helper environment](../../support/hsm/Makefile) and
scoped clients, run on a Linux workstation with approved swap protection and a YubiKey:

```sh
make -C clusters/trust secrets-rehearse
```

If needed, set `HSM_VENV` to the absolute path of the existing HSM environment.
The target verifies scoped clients and uses that environment's Python,
`homelab-wrap`, and `homelab-unwrap`. Follow the touch instructions; wrapping,
verification, recovery and the corruption check can require multiple touches.

The rehearsal generates disposable native Talos secrets and uses the shared
wrapping/recovery functions under `homelab/v1/trust/talos/rehearsal/r1`.
Plaintext stays in memory and pipes. Only ciphertext and Git fixture metadata
are written to a temporary isolated repository, removed on normal completion
or handled failure. An interrupted/killed process may leave disposable
ciphertext behind. The production record and manifest are never used.

Success requires an exact in-memory round trip, refusal to overwrite the
existing record, rejection of a one-bit ciphertext mutation, and rejection
of a missing record. Output contains public preflight/progress diagnostics,
touch instructions and pass/fail results,
never the secret bundle or a digest of it. Unit tests exercise orchestration
with disposable fixtures. The operator verified the pinned-tool/YubiKey rehearsal
on `simlun-x1` on 2026-11-07; see the [recorded results](../../docs/installation/02-trust.md#talos-secrets-lifecycle-point-3).

After updating the code submodule, reinstall the offline HSM environment with
`make -C support/hsm tools` before retrying a rehearsal. Both parent and HSM
subprocesses use the shared swap check. No `swapoff` is needed for an accepted
random-key encrypted mapping; unsupported or unreadable evidence remains an error.

## Offline configuration rehearsal

```sh
make -C clusters/trust config-rehearse
```

Requires the scoped clients and installed HSM environment used above, but no
YubiKey or private records. It generates a disposable Talos secret bundle, builds
a full control-plane configuration with the committed public patches, and runs
native strict validation and confirms malformed supplied secrets are rejected.
It then issues and reissues `os:admin` talosconfigs
from that same bundle and checks their context, roles and expiry through native
`talosctl config info` JSON output. This tests local credential preparation,
not authentication to a running node. Native generation currently issues
one-year client certificates. The agreed [routine policy](../../docs/security/security.md#trust-administration-credentials)
targets 24 hours; the separate credential rehearsal below implements that signer. Offline reissuance does not revoke earlier credentials. Kubernetes admin
access needs a bootstrapped API and is not tested here.

Inputs are private, anonymous Linux `memfd` descriptors sealed against changes;
outputs are captured through bounded pipes. Descriptors close on success or
failure, including process termination. No named plaintext files, output
configurations or credential records are created. Approved OS paging remains
required. Python does not guarantee zeroization of copies in process memory.

The endpoint `https://trust-rehearsal.invalid:6443` and installation selector
`/dev/REHEARSAL-DO-NOT-INSTALL` are test-only placeholders. This target has no
network operation, apply, installation or Kubernetes bootstrap command. It does
not establish KMS encryption, storage readiness, the production endpoint or
hardware behavior. Do not use its disposable identity for Trust provisioning.

The hostname patch explicitly sets `auto: off`: otherwise native merging retains
Talos's generated `auto: stable`, conflicting with the explicit hostname. The
same public render is used for inspection, native generation and CI.

The operator verified this target on `simlun-x1` (Linux amd64) on 2026-11-08.
See the [recorded results](../../docs/installation/02-trust.md#full-configuration-and-administration-credential-rehearsal)
for the verification scope and remaining production decisions.

The DNS record for the [production API endpoint](../../docs/network.md#kubernetes-api-endpoint)
is configured; resolution was verified on 2026-11-08. See the
[required DNS entries](../../docs/network.md#required-dns-entries). The rehearsal retains test-only
placeholders. Talos clients will be reissued from the wrapped bootstrap authority;
no separate wrapped administration record is planned.

## Protected 24-hour credential rehearsal

```sh
make -C clusters/trust credentials-rehearse
```

No YubiKey or private records are needed. The target generates a disposable CA
with native Talos tooling, issues an `os:admin` client using `gen key`, `gen csr`
and `gen crt --hours 24`, then uses native commands to assemble/inspect a
`talosconfig`. It verifies issuer signature and validity, client key match, role,
client-auth usage and expiry. The issuer accepts supplied CA PEM bytes; the
recovery rehearsal below extracts those bytes from a disposable wrapped bundle.
No production identity, node access, DNS, installation or apply is involved.

`RAM_ROOT` defaults to `/dev/shm`; override it only with an existing tmpfs
location, for example `RAM_ROOT="$XDG_RUNTIME_DIR"` when that is verified tmpfs.
The helper checks the opened directory's mount ID against Linux mountinfo,
creates an operator-owned `0700` subdirectory, and holds directory descriptors
so native paths remain anchored to that mount. Ordinary directories are rejected
before secret files are created. Child home/temp paths stay inside the workspace,
output is suppressed, and umask `077` protects generated files.

Each native process inherits a file-size limit of at most 1 MiB. After each
command the helper admits at most the seven expected private regular files;
unknown files, symlinks, exposed permissions or oversized output fail. CI adds
a dedicated 16 MiB tmpfs mount and disables networking for the rehearsal.
Approved OS swap protection remains required.

Workspaces are removed on success, exceptions, Ctrl-C, SIGTERM and SIGHUP.
SIGKILL or a crash can leave private RAM files until manual removal or reboot;
the helper prints each workspace path so a stopped operation can be cleaned up.
Do not use an ordinary temporary-directory fallback. Memory copies are not
physically zeroizable through Python. The operator verified this target on
`simlun-x1` (Linux amd64) on 2026-11-08 at commit `bd1e759`, using `/dev/shm`;
all checks and RAM workspace cleanup passed. See the
[verification record](../../docs/installation/02-trust.md#protected-24-hour-client-issuer).
Live Talos authentication is not tested.


## Wrapped recovery rehearsal

Refresh the helper environment for the new offline YAML dependency, then run:

```sh
make -C support/hsm tools
make -C clusters/trust recovery-rehearse
```

A YubiKey with the existing slot-2 golden key and approved swap protection is
required. `RAM_ROOT` has the same verified-tmpfs contract as credential issuance
above. The target uses only a disposable identity and isolated ciphertext Git
repositories; the production private submodule is not needed or accessed.

The helper generates and wraps one disposable Talos bundle, discards that input,
and recovers the ciphertext twice with YubiKey touch. Each recovered bundle feeds
native configuration generation with the committed public patches and strict
metal-mode validation, followed by native 24-hour `os:admin` client issuance.
PyYAML's safe loader reads existing `certs.os` material in memory; missing CA
fields fail before generation. The helper checks that the generated machine and
client use that CA, both recoveries return the original bundle, fresh client
certificates and keys differ, and the ciphertext remains unchanged.

Full machine configurations use sealed anonymous descriptors and pipes; native
signing files stay in private tmpfs workspaces. Successful completion removes
the temporary ciphertext repositories and RAM files. The cleanup and SIGKILL
limitations above also apply. No plaintext credential or configuration is printed.
Test-only endpoint and disk placeholders remain; this performs no node calls,
installation, apply, or production identity creation. The operator verified this
flow with the physical YubiKey on `simlun-x1` (Linux amd64) on 2026-11-08,
using `/dev/shm`; all checks and cleanup passed. See the
[verification record](../../docs/installation/02-trust.md#wrapped-recovery-and-reissuance-rehearsal). CI exercises this flow offline on tmpfs
using real record cryptography with the public fake responder; it cannot verify
the physical token or the workstation CLI integration.


## Administration client inspection

```sh
make -C clusters/trust admin-rehearse
```

This exercises the administration wrapper with a disposable authority and the
physical YubiKey. It uses the same private ciphertext Git fixture and tmpfs
requirements as `recovery-rehearse`. It recovers the wrapped bundle, issues a
fresh 24-hour `os:admin` client, inspects it locally and cleans up. The operator
verified this path on `simlun-x1` (Linux amd64) on 2026-11-08 with the physical
YubiKey and `/dev/shm`; all checks and cleanup passed. See the
[verification record](../../docs/installation/02-trust.md#operating-entry-points-point-5).
CI runs native issuance with the public fake responder.

Once a production bootstrap record has been deliberately initialized, use:

```sh
make -C clusters/trust admin-inspect
```

This requires the initialized private submodule and existing bootstrap record.
It never generates an identity, wraps a record, or overwrites the authority.
Missing records, failed recovery or invalid CA material stop the operation.
The context is `trust`; both Talos endpoint and target node come from the single
IPv4 address in the committed `trust-cp1` LinkConfig patch, independently of the
Kubernetes API DNS endpoint. Missing or ambiguous addresses are rejected.

The wrapper issues through the protected native signer and uses a sealed memfd
for local inspection. Only context, endpoint/node, roles and certificate dates
are printed; the talosconfig, private key and recovered bundle are never printed
or persisted. The same cleanup and paging limitations as the credential
rehearsal apply. Neither command contacts a node. Live command delivery remains
a later slice; this entry point currently supports local inspection only.
No production identity has been created by implementation or CI.


## Pi live-boot discovery

The [UEFI experiment](../../docs/installation/02-trust.md#discovery-scope-and-boot-artifacts)
selects pftf/RPi4 v1.53 and the generic ARM64 ISO for the Talos version in
`versions.yaml`, with reviewed SHA-256 values and manual download instructions.
Downloads and card-preparation working files belong in ignored `boot/`.
Start with candidate disks disconnected; reach UEFI setup before preparing the
separate ISO USB medium. Disk identities, adapter details and final assignments
will be recorded during inventory. No machine configuration is applied in this
phase; reaching maintenance mode does not establish encrypted installation or
pre-STATE KMS readiness. SD-first EEPROM configuration and the first UEFI setup
boot were operator-verified on 2026-11-08; see the
[experiment record](../../docs/installation/02-trust.md#experiment-record-and-acceptance-checks).
UEFI Firmware v1.53 and a repeat cold boot into setup were verified on
2026-11-09 without settings changes. Persistence of modified settings and
Talos hardware discovery remain pending.
