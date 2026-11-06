# Trust cluster

Independent foundational Kubernetes cluster, initially a single control-plane
node (`trust-cp1`, `10.10.0.10`). See the
[installation roadmap](../../docs/installation/02-trust.md).

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

The [Talos secret lifecycle](../../docs/installation/02-trust.md#talos-secrets-lifecycle-point-3) requires one-time native Talos generation, authenticated YubiKey wrapping and stable recovery of the same cluster identity. This is a design only: no production secret helper or deploy command is implemented yet.

The Raspberry Pi `eth0` interface name and UEFI behavior remain unverified.
Do not apply this partial public bundle to a node.

## Experimental bootstrap-secret CLI (Point 3)

`scripts/trust_talos_secrets.py` implements two explicit operations. This
script is **not** wired into production Make targets and does not apply Talos
configurations. The operator must provide full paths to the matching
`talosctl` binary (version read from `clusters/trust/versions.yaml`) and installed `homelab-wrap` or `homelab-unwrap`
from the pinned HSM environment. No ambient PATH fallback is accepted.

The private `secrets/wrapped/` submodule must be initialized and swap disabled.
The script disables core dumps/ptrace and suppresses subprocess error output.
Initialize **once**, on a workstation with a YubiKey and already verified
tooling (commands shown with illustrative executable locations):

```sh
python3 -I -B scripts/trust_talos_secrets.py init \\
  --talosctl /absolute/pinned/talosctl \\
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
A future provisioning consumer will take this stream directly into a
protected native Talos generation workflow. The current helper deliberately
does not offer an apply target.

Security limitations: ordinary workstation process memory is not physically
zeroizable through Python, and swap checks alone do not prove absence of all
OS dump mechanisms or instrumentation. Do not treat this as independently
audited protection. Initial generation/recovery must be exercised using
disposable secrets before the first real credential is created.
