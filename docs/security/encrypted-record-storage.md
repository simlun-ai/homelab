# Encrypted-record storage

**Private submodule and coordinator credential workflows implemented; production records and service deployment pending.**

## Authoritative records

Keep authenticated `homelab-wrap-v1` JSON records in the **private**
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
or updating credentials, create a uniquely named branch in the submodule:

```sh
git -C secrets/wrapped switch -c credential-update
```

Run the relevant credential helper. Review changes, then commit and push the
private repository **first** (example for one generated password):

```sh
git -C secrets/wrapped add ups-aux-administrator.json
git -C secrets/wrapped commit -m "Add ups-aux administrator password"
git -C secrets/wrapped push -u origin HEAD
git add secrets/wrapped secrets/manifest.json
git commit -m "Update wrapped credential reference"
git push
```

For SSH-key creation also stage `support/ups/coordinator_ed25519.pub` in the
parent. Never put ciphertext in the parent to work around missing private access.
Retain pushed private branches/commits referenced by the parent. After pulling
parent changes, repeat `git submodule update --init --recursive -- tools/homelab-hsm secrets/wrapped` to select both
pinned versions; do not use `--remote` for normal recovery. Rerun `make -C support/hsm tools` after changing the code-submodule version; it installs the matching committed wheels offline into the external environment. Record-only updates do not require reinstalling Python. Preserve uncommitted
changes before switching versions.

## Coordinator deployment

Deploy required wrapped KMS, DNS, TLS and ACME records to coordinator-local
persistent storage. Startup must not fetch GitHub or OpenBao. Base Ansible is
implemented; record deployment remains pending under
[01 - Main coordinator](../installation/01-main-coordinator.md).
The password helper instead streams a password to the Pi, which stores its
normal account hash; SSH deployment installs only the public key.

Git history retains old ciphertext in the private repository.
Retention, rotation and rollback policy belongs to [rotation and rollback](rotation-and-rollback.md).
