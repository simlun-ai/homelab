# Coordinator administrator passwords

**Workflow implemented; real records and Pi verification pending.** Each Pi has
its own randomly generated 43-character password (32 random bytes encoded as
URL-safe Base64). The repository owns the YubiKey-wrapped records. SSH continues
to use the [repository-owned shared SSH key](coordinator-ssh-key.md),
public-key authentication only, and passwordless sudo. These passwords are for local console access and recovery;
SSH key generation and agent loading belong to that separate runbook.

## Prepare

Initialize the [private secrets submodule](../docs/security/encrypted-record-storage.md#checkout-and-updates) before generating or recovering records. Rerun `make -C support/yubikey tools` after submodule updates to install the matching private library and dependencies.

Complete [YubiKey setup and verification](../docs/installation/00-yubikey-setup.md)
first. Use a trusted Linux workstation, an unrecorded local terminal and one
verified token. Install the pinned token tooling:

```sh
make -C support/yubikey system-dependencies
make -C support/yubikey tools
```

Follow the [memory-only policy](../docs/security/security.md#secret-handling-boundary).
Do not use terminal/session recording, clipboard history, shell tracing or saved
Imager credentials. Do not suspend/hibernate while secrets are in memory; ensure
this workstation's swap cannot persist secrets. This is separate from step 00's
explicit air-gapped laptop exception. The helper disables its core dumps and
process dumping, requires a terminal, suppresses SDK logs and exception details,
and never explicitly writes plaintext to disk. It does not configure the OS or
guarantee Python memory zeroization.

## Create once, then preserve

From the repository root:

```sh
make -C support/ups password-create HOST=ups-aux
make -C support/ups password-create HOST=ups-pi
make -C support/ups password-create HOST=ups-metal
```

Touch when prompted. Each operation wraps a fresh random password using OTP
slot 2 and verifies it by decrypting it before writing ciphertext. Existing
records are never overwritten. The public [manifest](../secrets/manifest.json)
lists the password identifiers, root generation and filenames; an entry does
not mean its record has been created or applied. The helper independently fixes
those expected contexts rather than trusting metadata in a supplied record.

Commit and push the three generated JSON records in the private submodule,
then commit its updated pointer in `homelab`, following the [storage workflow](../docs/security/encrypted-record-storage.md#checkout-and-updates).
Refresh all four recovery USB clones before relying on the passwords. No plaintext passwords or password
hashes belong in Git. Preserve the records when reinstalling a Pi.

## Use during installation or recovery

Explicitly reveal only the selected password:

```sh
make -C support/ups password-reveal HOST=ups-aux
```

Confirm `reveal`, touch the token, then manually enter the result at the Pi's
local console or into Imager if an initial password is required. Do not redirect
output, copy it into commands, save presets, or use a recorded/shared terminal.
Close the terminal afterwards; clearing the display is not secure erasure.
Validate Imager's handling on the first installation; the helper does not manage
its caches. If Imager persists credentials, use a disposable initial password
and replace it with the wrapped password after bootstrap and hardening.

## Apply to an existing coordinator

After the [base setup](ups-coordinator-base-setup.md), manual reboot and successful
`verify-hardening`, load the [shared SSH key](coordinator-ssh-key.md#load-before-management-operations)
into the local agent, then run from the management subnet:

```sh
make -C support/ups password-apply HOST=ups-aux
```

Repeat for `ups-pi` and `ups-metal`. The hostname must resolve in workstation
DNS or SSH config, even if Ansible uses an `ansible_host` override. Verify its SSH
host key first. The helper unwraps in memory and streams the password through
key-authenticated SSH to `sudo -n /usr/sbin/chpasswd`. SSH allocates no terminal;
remote output is suppressed. Do not enable sudo/PAM input logging for this
operation. [chpasswd](https://manpages.debian.org/trixie/passwd/chpasswd.8.en.html)
uses the Pi's PAM password policy and persists the account's salted hash in its
system password database; plaintext is not deployed as a file. Ansible leaves
this password alone.

Verify local console login while keeping your existing SSH session available.
Record success per host without recording the password. Reapplying the same
record sets the same password, although its salted hash/password age may change.
If delivery fails or times out, it may already have succeeded; retry the same
record. A missing, malformed or tampered record must be recovered from a trusted
clone, not replaced with a freshly generated password by accident. An incomplete
ciphertext file from interrupted creation is not usable: preserve/inspect it
before removing it and retrying creation. No host is modified during creation.

Rotation is a separate maintenance operation under the
[rotation policy](../docs/security/rotation-and-rollback.md); this initial helper
intentionally has no overwrite/rotation command. Git history retains ciphertext.

