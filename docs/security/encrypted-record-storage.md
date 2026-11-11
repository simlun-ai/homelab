# Encrypted-record storage

**Private submodule and coordinator credential workflows implemented; production shared SSH key and all three coordinator passwords generated and committed. Service deployment pending.**

## Authoritative records

Except for coordinator-local ACME/TLS state described below, keep authenticated
`homelab-wrap-v1` JSON records in the **private**
`simlun-ai/homelab-secrets` repository, mounted at `secrets/wrapped`.
Shared cryptography, read-only token access, the CLI, dependency pins, offline
bundles, and tests live separately in `simlun-ai/homelab-hsm`, mounted at
`tools/homelab-hsm`. The Python project remains named `homelab-secrets`, with
imports under `homelab_secrets`; these names do not identify the records repository.
The parent pins both submodules and stores no credential ciphertext itself.
The parent and code repositories are public. The records repository must remain private.

The public `secrets/manifest.json` lists identifiers, root generations and
paths relative to `secrets/`. Entries reserve filenames and do not imply records
exist or are deployed. There are no manifest checksums. Schema belongs to
[helper implementation](helper-implementation.md); cryptographic validation and
memory-only handling remain governed by [security.md](security.md).

Wrap and verify in memory before writing ciphertext. Never persist plaintext,
password hashes, private keys, HMAC responses, derived keys, or golden-key
material in any of the three repositories. Public SSH keys remain in the parent repository.
The first consumers are [coordinator passwords](../../runbooks/coordinator-passwords.md)
and the [shared SSH identity](../../runbooks/coordinator-ssh-key.md).

No production credential records were present at the split. Do not share a
recursive working-directory copy: it includes private files.

## Checkout and updates

For documentation, code installation, and tests, initialize only the code:

```sh
git clone https://github.com/simlun-ai/homelab.git
cd homelab
git submodule update --init --recursive -- tools/homelab-hsm
```

These commands do not require private access.
Operators additionally initialize the private records checkout:

```sh
git submodule update --init --recursive -- secrets/wrapped
git submodule status -- tools/homelab-hsm secrets/wrapped
```

GitHub access uses separately configured Git credentials, not the wrapped
coordinator SSH identity. Helpers reject a missing records checkout before
credential generation or recovery, and reject an unrelated old code checkout
at that path. New private credential commits descended from the parent pin are
allowed. Token setup and automated tests do not need
it; integration tests use public dummy material in temporary repositories.

The checkout is normally detached at the parent-pinned commit. Before generating
or updating credentials, switch to the private repository's `main` and update it:

```sh
git -C secrets/wrapped fetch origin
git -C secrets/wrapped switch main
git -C secrets/wrapped pull --ff-only origin main
```

Run the relevant credential helper. Review changes, then commit and push the
private repository's `main` **first**, then the parent pointer. For SSH-key creation,
first run `git add support/ups/coordinator_ed25519.pub` in the parent so the public
key is included in the same parent commit. Stage `secrets/manifest.json` only if
you changed its entries; credential generation does not update it.

```sh
git -C secrets/wrapped add -A
git -C secrets/wrapped commit
git -C secrets/wrapped push origin main
git add secrets/wrapped
git commit -m "Update wrapped credential reference"
git push
```

Never put ciphertext in the parent to work around missing private access.
Keep parent-pinned private commits reachable from the private repository's `main`.
After pulling
parent changes, repeat `git submodule update --init --recursive -- tools/homelab-hsm secrets/wrapped` to select both
pinned versions; do not use `--remote` for normal recovery. Rerun `make -C support/hsm tools` after changing the code-submodule version; it installs the matching committed wheels offline into the external environment. Record-only updates do not require reinstalling Python. Preserve uncommitted
changes before switching versions.

## Coordinator deployment

Deploy required wrapped KMS and DNS records to coordinator-local persistent
storage. ACME/TLS state is generated and retained locally as described below. Startup must not fetch GitHub or OpenBao. Base Ansible is
implemented; record deployment remains pending under
[01 - Main coordinator](../installation/01-main-coordinator.md).
The password helper instead streams a password to the Pi, which stores its
normal account hash; SSH deployment installs only the public key.

Git history retains old ciphertext in the private repository.
Retention, rotation and rollback policy belongs to [rotation and rollback](rotation-and-rollback.md).

## ACME state replacement

Normal ACME startup recovers wrapped state. Initialization refuses an existing
record; explicit recreation creates new ACME/TLS identity material. Missing or
corrupt state is never an implicit recreation request. Verify the newly wrapped
replacement before archiving and atomically replacing the previous ciphertext.
An archive failure prevents replacement. If the old state is unavailable,
explicit recreation reports that no archive can be made. Node KMS keys and Talos
authority are outside this operation.

The [staging implementation](../installation/trust-kms-cloudflare.md#wrapped-staging-state-initialize-recover-and-recreate)
keeps current ciphertext and archives solely under the coordinator's root-owned
`/var/lib/trust-kms/acme-staging/`. The explicit production profile uses
`/var/lib/trust-kms/acme-production/`, a separate current filename and wrapping
context. Production initialization/recovery is implemented but not yet verified
on the coordinator. Neither environment has a private manifest entry. The
workstation fetches ciphertext over
verified SSH, unwraps in memory with the YubiKey, and streams recovered state
back to protected coordinator RAM. Updated state is wrapped/verified on the
workstation, then sent back as ciphertext. Compare-and-replace publication on
the Pi rejects stale sessions. There are no ACME records in the public manifest
or required Git copies. Losing the SD card is handled by explicit recreation
using the separately preserved Cloudflare token. Old local staging copies may
be imported; no automatic deletion or history rewrite occurs.

This coordinator-local custody decision applies to ACME/TLS identity material,
not node KMS keys or Talos authority. Production listener and process-lifetime integration remain pending.
No raw HMAC response or wrapping key is retained for unattended record updates;
each state publication requires fresh workstation/YubiKey operations.
