# Encrypted-record storage

**Private submodule and coordinator credential workflows implemented; production records and service deployment pending.**

## Authoritative records

Keep authenticated `homelab-wrap-v1` JSON records in the **private**
`simlun-ai/homelab-wrapped-secrets` repository, mounted as the Git submodule
`secrets/wrapped`. Keep it private even if `homelab` becomes public. The parent
tracks only the submodule URL and commit, not ciphertext files.

The public `secrets/manifest.json` lists identifiers, root generations and
paths relative to `secrets/`. Entries reserve filenames and do not imply records
exist or are deployed. There are no manifest checksums. Schema belongs to
[helper implementation](helper-implementation.md); cryptographic validation and
memory-only handling remain governed by [security.md](security.md).

Wrap and verify in memory before writing ciphertext. Never persist plaintext,
password hashes, private keys, HMAC responses, derived keys, or golden-key
material in either repository. Public SSH keys remain in the parent repository.
The first consumers are [coordinator passwords](../../runbooks/coordinator-passwords.md)
and the [shared SSH identity](../../runbooks/coordinator-ssh-key.md).

Moving files into a submodule does not erase parent Git history. No production
credential records were present at the split; before publishing the parent,
review its complete history and any locally created commits for sensitive data.
Do not share a recursive working-directory copy: it includes the private files.

## Checkout and updates

From an existing parent checkout, with GitHub access to the private repository:

```sh
git submodule update --init --recursive -- secrets/wrapped
git submodule status -- secrets/wrapped
```

For a new checkout, `git clone --recurse-submodules git@github.com:simlun-ai/homelab.git`
fetches both. Public readers can clone the parent without recursion; docs,
manifest tests and non-secret checks do not require private access. GitHub
access uses your separately configured Git credentials, not the wrapped
coordinator SSH identity. Helpers fail clearly if the submodule is absent.

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
parent changes, repeat `git submodule update --init --recursive` to select its
pinned version; do not use `--remote` for normal recovery. Preserve uncommitted
changes before switching versions. Refresh all four recovery USBs after updates.

## Recovery USB clones

Each YubiKey's paired USB needs **complete, non-shallow clones of both repositories**,
the public manifest, this documentation, and the pinned secrets checkout. A plain
parent clone or source archive is insufficient. Never embed Git access tokens.

For a new USB copy, start in a clean, committed parent checkout with the private
submodule initialized at the pinned version. Confirm both shallow checks print
`false`, and that submodule status has no leading `-`, `+`, or `U`:

```sh
git rev-parse --is-shallow-repository
git -C secrets/wrapped rev-parse --is-shallow-repository
git submodule status -- secrets/wrapped
```

Replace `/media/RECOVERY` with the mounted USB. Both destination directories must
be new. These copies use only local Git objects, so no network is needed:

```sh
git clone --no-hardlinks . /media/RECOVERY/homelab
git clone --no-hardlinks secrets/wrapped /media/RECOVERY/homelab/secrets/wrapped
git -C /media/RECOVERY/homelab/secrets/wrapped checkout --detach "$(git rev-parse HEAD:secrets/wrapped)"
git -C /media/RECOVERY/homelab submodule absorbgitdirs secrets/wrapped
git -C /media/RECOVERY/homelab remote set-url origin git@github.com:simlun-ai/homelab.git
git -C /media/RECOVERY/homelab/secrets/wrapped remote set-url origin git@github.com:simlun-ai/homelab-wrapped-secrets.git
```

Verify offline:

```sh
git -C /media/RECOVERY/homelab fsck --full
git -C /media/RECOVERY/homelab/secrets/wrapped fsck --full
git -C /media/RECOVERY/homelab rev-parse --is-shallow-repository
git -C /media/RECOVERY/homelab/secrets/wrapped rev-parse --is-shallow-repository
git -C /media/RECOVERY/homelab rev-parse HEAD
git -C /media/RECOVERY/homelab submodule status -- secrets/wrapped
```

Record both commit IDs; confirm the pinned checkout and required credential files
are present. A successful clone or fsck does not prove production credentials have
been generated. For a refresh, prepare a new destination and retain the previous
verified kit until replacement checks pass. Recovery tool binaries/dependencies
still need the independent packaging in [recovery procedures](recovery-procedures.md);
a clone alone does not establish offline executability.

## Coordinator deployment

Deploy required wrapped KMS, DNS, TLS and ACME records to coordinator-local
persistent storage. Startup must not fetch GitHub or OpenBao. Base Ansible is
implemented; record deployment remains pending under
[01 - Main coordinator](../installation/01-main-coordinator.md).
The password helper instead streams a password to the Pi, which stores its
normal account hash; SSH deployment installs only the public key.

Git history retains old ciphertext in the private repository.
Retention, rotation and rollback policy belongs to [rotation and rollback](rotation-and-rollback.md).

