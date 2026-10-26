# Helper implementation

**Initial token setup and wrapping helpers implemented; hardware verification and service helpers pending.**

[Step 00](../installation/00-yubikey-setup.md) owns the executable setup and verification procedure. Token programming and application consumers live under `scripts/homelab/`. Shared wrapping, read-only token access, and the `homelab-wrap`/`homelab-unwrap` commands live in `tools/homelab-hsm/homelab_secrets/`, a separate code submodule. Its `pyproject.toml` owns crypto/token dependency pins; `support/yubikey/` installs it locally into the scoped virtualenv. The coordinator password and SSH key workflows use `secrets/wrapped/`; real records require local token-backed generation. Coordinator KMS services and OpenBao integration remain pending.

## Workstation helper

The `homelab_secrets` library exposes bytes-based `wrap`/`unwrap` with an injectable HMAC response callback and no parent-repository or manifest dependency. The implemented CLI wraps and verifies before exclusive ciphertext creation; unwrap requires explicit expected context and either confirmed escaped terminal reveal or explicit stdout to a pipe/socket. Plaintext file redirection is rejected. See the [package README](../../tools/homelab-hsm/homelab_secrets/README.md) for installation and usage.

Parent helpers reuse the library. Existing and planned consumers cover:

- Wrap and verify credential records.
- Unseal OpenBao over verified TLS.
- Deliver ZFS keys directly to the unlock command.
- Authorize the coordinator over SSH.
- Verify token behavior without printing secret responses.
- Perform explicit software recovery using the golden key from Level 1.

Pin dependencies and compatible hardware tools. Validate records and
expected identifiers before querying a token. Bound input sizes and
deliver plaintext directly to its consumer, with no default plaintext
output.

Keep secrets out of arguments, environment variables, temporary files,
and logs. Follow the
[memory-only policy](security.md#secret-handling-boundary).
Package recovery dependencies for use without downloads.

## Coordinator password helper

`scripts/homelab/coordinator_password.py` reuses the shared wrapping library and token
adapter through `scripts/coordinator_password_cli.py`. Commands and failure recovery
are in the [runbook](../../runbooks/coordinator-passwords.md).

`secrets/manifest.json` is public metadata: `format` is
`homelab-wrapped-manifest-v1`; `records` is a list of objects with exact `key_id`,
`root_key`, and `file` (path relative to `secrets/`, starting with `wrapped/`). The helper fixes
expected contexts independently in code. Manifest/code agreement is tested;
entries do not attest to existence, deployment, or freshness. Initial records
use revision 1. No checksums are maintained. Overwriting and rotation are not implemented.
Both credential helpers require an initialized Git submodule at `secrets/wrapped`
before reading or generating records; missing checkout errors precede token access.
Public documentation and agent-only checks do not require private access. The full helper test suite requires the installed code package, not the private records checkout.

`make -C support/yubikey test` also runs the parent/library contract tests in
`tests/test_wrapped_secrets_integration.py`: complete JSON records, manifest
identifiers, malformed/tampered input, and the password/SSH consumers. These use
the public `golden-fake-1` software responder without mocking cryptography;
consumer tests retain their production context identifiers inside temporary test
repositories. No real token, credential, or SSH connection is used.

## Coordinator SSH helper

`scripts/homelab/coordinator_ssh.py` generates one Ed25519 identity using the
existing pinned cryptography library. It serializes a passphrase-less OpenSSH
private key in memory, wraps and verifies it, then persists ciphertext and the
public half. The manifest uses the same schema as passwords. Loading authenticates
the record and checks the public/private match before streaming to `ssh-add`;
`ssh-add -T` checks agent signing. No private-key export command is provided.
The [runbook](../../runbooks/coordinator-ssh-key.md) owns operations and recovery.

## Vault KMS: two layers

Generate a random 32-byte KMS key per Vault node. Protect it as a normal
`homelab-wrap-v1` record using the YubiKey foundation.

The workstation unwraps that key and sends it over SSH to the coordinator.
The coordinator retains it for the authorized one-hour window under the
[session policy](coordinator-sessions.md).

The KMS key protects Talos disk unlock secrets. The coordinator receives
neither the golden key nor raw YubiKey responses.

The Talos KMS protocol supplies a node UUID and payload, without a volume
identifier. Use one KMS key per node for its system-volume payloads;
final lookup identifiers belong in the [catalogue](yubikey.md).

### Why Seal and Unseal exist

During initial encrypted-disk preparation, Talos generates an unlock
secret and sends it to KMS using `Seal`. KMS encrypts it and returns a
protected payload, which Talos stores in the disk's LUKS metadata.

On subsequent boots, Talos sends that payload to KMS using `Unseal`.
KMS decrypts it and returns the unlock secret.

These operations protect Talos unlock material. They are separate from
OpenBao's unseal process.

### KMS payload encryption

For each `Seal`, generate fresh random salt and nonce, derive a payload
key from the node's KMS key using HKDF-SHA-256, and encrypt with
AES-256-GCM.

Return a versioned `homelab-kms-v1` envelope authenticating its format,
node UUID, KMS-key generation, salt, and nonce. `Unseal` validates the
envelope and request context before deriving the same key and decrypting.

This envelope is distinct from `homelab-wrap-v1`, which protects the
node's KMS key. Exact envelope fields, encodings, HKDF context, and
validation limits must be specified before implementation.

## Keys: where and when

| Secret | Persistent storage | Plaintext lifetime |
| --- | --- | --- |
| Golden key | Four YubiKeys; backup in Level 1 | Used inside the token normally; workstation memory during programming or software recovery. |
| YubiKey response and wrapping key | None | Briefly in workstation memory while wrapping or unwrapping. |
| Node KMS key | Wrapped record in Git, recovery USB clones, and coordinator local storage | Briefly on the workstation; coordinator memory for the authorized hour. |
| Talos disk unlock secret | KMS-encrypted payload in disk LUKS metadata | Talos memory during setup/unlock; coordinator memory only while processing the request. |
| Derived KMS payload key | None | Coordinator memory only while processing Seal or Unseal. |
| LUKS volume encryption key | Protected by LUKS keyslots on the node | Node memory while the volume is unlocked; never sent to the coordinator. |
| DNS/TLS/ACME credentials | Wrapped records under the storage policy | Briefly on the workstation during delivery; coordinator process lifetime. |

### Lifecycle

1. **KMS setup:** Generate the node KMS key in workstation memory,
   wrap and verify it using the YubiKey, and persist only the encrypted
   record. Deploy that record to the coordinator.
2. **Authorization:** Unwrap the key on the workstation and send it
   over SSH. Discard workstation secrets after successful delivery.
3. **Initial disk setup:** Talos calls Seal and stores the returned
   protected payload in LUKS metadata.
4. **Later boots:** Talos calls Unseal with that stored payload.
5. **Expiry or lock:** The coordinator rejects further KMS operations
   and discards the node KMS key, derived keys, and secret copies.
   Already unlocked volumes continue running.
6. **Next authorization:** Recover the same node KMS key from its
   wrapped record; do not generate a replacement for existing disks.

Retain older KMS-key generations while disks or retained recovery
material depend on them. Replacing a KMS key requires migration;
a new random key cannot decrypt existing payloads.

## Remaining implementation work

- Specify the KMS envelope and SSH delivery protocol.
- Extend dependency pins and offline recovery packaging for the service helpers.
- Implement memory handling, consumer delivery, and failure cleanup.
- Test malformed/tampered records, identifier and node substitution,
  touch enforcement, session expiry, and independent recovery.

Python object deletion alone does not guarantee secret zeroization;
verify process isolation and cleanup against the memory-only policy.

## References

- [Talos KMS protocol](https://github.com/siderolabs/kms-client/blob/main/api/kms/kms.proto).
- [Wrapped-record storage](encrypted-record-storage.md).
- [YubiKey setup](yubikey-setup.md).
