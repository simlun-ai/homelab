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
The parent and code repositories are intended to be public; changing their
GitHub visibility is a separate administrative step. The records repository
must remain private.

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

After the code repositories become public these commands need no private access.
Until then, use your existing GitHub authentication; an SSH-only setup can use
`git clone git@github.com:simlun-ai/homelab.git` and
`git -c url.git@github.com:.insteadOf=https://github.com/ submodule update --init --recursive -- tools/homelab-hsm`.
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

### Migrate an existing checkout

The repository behind `secrets/wrapped` has changed from the renamed code
repository to the new records repository. Use a fresh sibling checkout rather
than reusing the old submodule's Git directory:

```sh
git clone git@github.com:simlun-ai/homelab.git ../homelab-split
cd ../homelab-split
git -c url.git@github.com:.insteadOf=https://github.com/ submodule update --init --recursive -- tools/homelab-hsm secrets/wrapped
make -C support/yubikey tools
make -C support/yubikey test
```

Use a new destination name, preserve uncommitted work, and retain the old checkout
until the replacement passes. Do not copy the old code checkout into the new
records repository. Existing record filenames and manifest entries are unchanged.
No production records need moving for this split. Refresh recovery USBs using
new destinations as described below.

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
pinned versions; do not use `--remote` for normal recovery. Rerun `make -C support/yubikey tools` during online preparation after changing the code-submodule version; it refreshes the local package and its dependencies. Record-only updates do not require reinstalling Python. Preserve uncommitted
changes before switching versions. Refresh all four recovery USBs after updates.

## Recovery USB clones

Each YubiKey's paired USB needs **complete, non-shallow clones of all three
repositories**, both submodules at their pinned commits, the public manifest,
and this documentation. A parent-only clone or source archive is insufficient.
Never embed Git access tokens.

Start from a clean, committed checkout with both submodules initialized. Confirm
all three shallow checks print `false`, and submodule status has no leading
`-`, `+`, or `U`:

```sh
git rev-parse --is-shallow-repository
git -C tools/homelab-hsm rev-parse --is-shallow-repository
git -C secrets/wrapped rev-parse --is-shallow-repository
git submodule status -- tools/homelab-hsm secrets/wrapped
```

Replace `/media/RECOVERY` with the mounted USB. Use a new destination. These
copies use local Git objects only and need no network:

```sh
git clone --no-hardlinks . /media/RECOVERY/homelab
git clone --no-hardlinks tools/homelab-hsm /media/RECOVERY/homelab/tools/homelab-hsm
git clone --no-hardlinks secrets/wrapped /media/RECOVERY/homelab/secrets/wrapped
git -C /media/RECOVERY/homelab/tools/homelab-hsm checkout --detach "$(git rev-parse HEAD:tools/homelab-hsm)"
git -C /media/RECOVERY/homelab/secrets/wrapped checkout --detach "$(git rev-parse HEAD:secrets/wrapped)"
git -C /media/RECOVERY/homelab submodule init -- tools/homelab-hsm secrets/wrapped
git -C /media/RECOVERY/homelab submodule absorbgitdirs tools/homelab-hsm secrets/wrapped
git -C /media/RECOVERY/homelab remote set-url origin git@github.com:simlun-ai/homelab.git
git -C /media/RECOVERY/homelab/tools/homelab-hsm remote set-url origin https://github.com/simlun-ai/homelab-hsm.git
git -C /media/RECOVERY/homelab/secrets/wrapped remote set-url origin git@github.com:simlun-ai/homelab-secrets.git
```

Verify offline:

```sh
git -C /media/RECOVERY/homelab fsck --full
git -C /media/RECOVERY/homelab/tools/homelab-hsm fsck --full
git -C /media/RECOVERY/homelab/secrets/wrapped fsck --full
git -C /media/RECOVERY/homelab rev-parse --is-shallow-repository
git -C /media/RECOVERY/homelab/tools/homelab-hsm rev-parse --is-shallow-repository
git -C /media/RECOVERY/homelab/secrets/wrapped rev-parse --is-shallow-repository
git -C /media/RECOVERY/homelab rev-parse HEAD
git -C /media/RECOVERY/homelab submodule status -- tools/homelab-hsm secrets/wrapped
```

Record all three commit IDs; confirm required records and
`tools/homelab-hsm/homelab_secrets/` are present. Clone/fsck success does not prove
production credentials exist. For refreshes, retain the previous verified kit
until replacement checks pass. The code submodule includes standalone offline
wheel bundles; preparing and verifying the complete recovery environment still
belongs to [recovery procedures](recovery-procedures.md).

## Coordinator deployment

Deploy required wrapped KMS, DNS, TLS and ACME records to coordinator-local
persistent storage. Startup must not fetch GitHub or OpenBao. Base Ansible is
implemented; record deployment remains pending under
[01 - Main coordinator](../installation/01-main-coordinator.md).
The password helper instead streams a password to the Pi, which stores its
normal account hash; SSH deployment installs only the public key.

Git history retains old ciphertext in the private repository.
Retention, rotation and rollback policy belongs to [rotation and rollback](rotation-and-rollback.md).
