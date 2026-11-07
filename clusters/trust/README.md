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

The [Talos secret lifecycle](../../docs/installation/02-trust.md#talos-secrets-lifecycle-point-3) requires one-time native Talos generation, authenticated YubiKey wrapping and stable recovery of the same cluster identity. An experimental bootstrap-secret helper exists below; administration credential recovery and deployment remain unimplemented.

The Raspberry Pi `eth0` interface name and UEFI behavior remain unverified.
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
with disposable fixtures; actual pinned-tool/YubiKey verification remains
pending until the operator runs this command and records the result.

After updating the code submodule, reinstall the offline HSM environment with
`make -C support/hsm tools` before retrying a rehearsal. Both parent and HSM
subprocesses use the shared swap check. No `swapoff` is needed for an accepted
random-key encrypted mapping; unsupported or unreadable evidence remains an error.
