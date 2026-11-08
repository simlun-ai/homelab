# Security

**YubiKey foundation verified; service integrations remain in progress.** Initial token programming, cross-token/software checks and independent replica retrieval passed on 2026-11-04; [step 00](../installation/00-yubikey-setup.md) records the scope.

## Secret-handling boundary

Helpers must never commit plaintext secrets, golden-key material, HMAC responses, or derived keys, or explicitly write them to workstation disk, including ignored files, temporary files, caches, shell history, logs, saved plans, local state, and crash dumps. Use process memory or streams; account for subprocesses and failure paths.

**Workstation swap decision (2026-11-07):** Secret-handling processes may use
swap only when every active area is verified as RAM-only zram without writeback,
or an active plain dm-crypt mapping matching a root-owned, writable only by root user/group
`/etc/crypttab` entry with a random key source (`/dev/urandom` or `/dev/random`).
This permits encrypted OS paging; it does not permit applications to write
plaintext files, caches or logs. Unprotected or unverified swap, including swap
files and persistent-key configurations not covered by this check, is rejected.
No swap is also accepted. Never hibernate while secrets are resident.

The shared `homelab_secrets.swap.require_safe_swap()` check runs before secret
operations in HSM CLI hardening and Trust's helper. It checks `/proc/swaps`,
active sysfs mapping identity/backing devices and crypttab configuration without
root execution, key access or `dmsetup table`. It trusts normal activation by
the root-controlled OS: these checks cannot prove which key was used to open an
existing mapping, prevent later privileged reconfiguration, or protect against a
compromised running host. Containers/VMs must expose enough evidence for every
relevant paging layer; unreadable or incomplete evidence fails closed. Core dump,
logging and explicit-file restrictions remain in force. Coordinator hosts retain
their stricter [RAM-only policy](coordinator-hardening.md).

[Step 00](../installation/00-yubikey-setup.md) runs inside the offline level1vault live OS. Its environment policy belongs to level1vault; helpers disable core dumps and keep decrypted keys in memory/streams. Other recovery environments, including the temporary OpenBao container, still require their documented memory-storage checks.

Authenticated `homelab-wrap-v1` credential records may be committed and persisted on workstation disk, and consuming hosts under the [encrypted-record storage policy](encrypted-record-storage.md). Decryption remains memory-only.

Public challenges, secret references, and protocol metadata may be committed. HMAC responses, derived values, golden-key material, and plaintext credentials or unseal/recovery material are secret. Keep them out of documentation, fixtures, and test output.

Encrypted persistence in cluster services, remote state, and backups is allowed, including protected Talos state, appropriately encrypted Kubernetes secret storage, and OpenBao storage. Transport must not stage decrypted secrets or OpenBao snapshots on workstation disk. The separately held offline golden-key record is encrypted by pass inside level1vault's encrypted workspace, outside these code and wrapped-record repositories.

Trust's offline configuration rehearsal supplies native Talos inputs using
private anonymous `memfd` descriptors with write/grow/shrink seals and close-on-exec,
inheriting only the required descriptors into each child. Output stays in bounded
pipes/process memory. This avoids named plaintext files and a separate mounted
workspace for that workflow; approved OS paging and existing dump/hibernation
restrictions still apply. Python memory copies are not guaranteed zeroizable.

## Core-secret foundation

**Decision:** The **20-byte golden key** held in the four [inventory YubiKeys](../inventory.md#security-keys) is the root of trust for **all homelab secrets**, through **OTP HMAC-SHA1 challenge-response**. Secrets are derived from its responses, wrapped under response-derived keys, or protected by OpenBao, whose unseal material is wrapped under this foundation. Generated or externally issued secrets are not necessarily deterministic derivatives of the golden key.

We treat the YubiKeys as **mini hardware security modules (HSMs)** for the homelab: they hold the golden key and perform HMAC-SHA1 challenge-response on-device, with physical touch required.

- Program all four with the same **golden key** and challenge-processing settings: identical effective challenge bytes must produce identical responses.
- Require physical touch for every hardware challenge-response operation.
- Keep the tokens at four separate locations.
- Keep the golden key separately offline for replacement-token programming and software recovery.
- Use OTP slot 2 under the [approved setup](yubikey-setup.md). Inspect before programming; overwriting occupied slot 2 requires the explicit replacement confirmation in [step 00](../installation/00-yubikey-setup.md). Preserve slot 1.

These are interchangeable copies of one HMAC secret, providing location redundancy rather than a multi-token threshold. OpenBao uses the [approved one-share, threshold-one Shamir design](openbao-unseal.md).

Verify programming/query tools and matching behavior on every actual device, including older Standard models; one modern CLI may not support all models.

## Golden key and software recovery

Generate the golden key once with suitable randomness and handle it only in memory during programming. Never display, log, or export it to the checkout. The generator emits it only to a pipe for encrypted storage.

The offline record enables replacement tokens and software recovery. The fallback must reproduce the exact effective challenge bytes, HMAC-SHA1 operation, and subsequent derivation/unwrap steps. It cannot enforce touch: possession of the golden key gives access to the entire foundation.

Store golden-key generations in the existing air-gapped, replicated Level 1 Password Management system under the [custody policy](golden-key-custody.md). Loading a key into a recovery workstation must follow the memory-only rule; initial replica retrieval and token verification passed; future service-recovery drills remain separate.

## Challenges, derivation, and wrapped credentials

**Decision:** Use HKDF-SHA-256 and AES-256-GCM for direct YubiKey wrapping, with the `homelab-wrap-v1` JSON record below. The initial shared helper is implemented for [step 00](../installation/00-yubikey-setup.md); physical-token verification passed on all four devices; production integrations remain pending. The [YubiKey catalogue](yubikey.md) owns identifiers, challenge construction, consumers, and unresolved bootstrap coverage; OTP slot 2 is selected under the [approved setup](yubikey-setup.md).

### Derivation and encryption

Use the raw 20-byte HMAC-SHA1 response as HKDF input; decode any tool's hexadecimal output first. For each encryption, generate a fresh 32-byte salt and 12-byte nonce using the operating system's cryptographic RNG. Both are public. Never reuse an AES-GCM key/nonce pair.

```text
response = YubiKey(challenge(key_id))
info = ASCII("homelab-wrap-v1") || NUL || ASCII(root_key) || NUL || ASCII(key_id)
wrapping_key = HKDF-SHA-256(input=response, salt=salt, info=info, length=32)
header = record without ciphertext
aad = UTF8(JCS(header))
ciphertext = AES-256-GCM.encrypt(wrapping_key, nonce, secret_bytes, aad)
```

`||` means byte concatenation; `NUL` is one zero byte. Use full HKDF extract-and-expand. JCS is RFC 8785 JSON canonicalization. Encrypt the credential's native bytes directly and retain the full 16-byte authentication tag, appended to the ciphertext.

A fresh salt derives a new wrapping key for each encryption of a credential. The protocol label, golden-key generation, and complete identifier in `info` separate contexts. A 32-byte output does not increase the entropy of the 160-bit foundation.

### Encrypted record

Illustrative placeholders, not an actual encrypted record:

```json
{
  "format": "homelab-wrap-v1",
  "root_key": "golden-1",
  "key_id": "homelab/v1/support-trust-backup/dns-api/cloudflare/r1",
  "revision": 1,
  "salt": "<base64: 32 bytes>",
  "nonce": "<base64: 12 bytes>",
  "ciphertext": "<base64: ciphertext followed by 16-byte tag>"
}
```

The format fixes the algorithms, sizes, and encodings; no per-record algorithm negotiation. `root_key` is a public golden-key-generation label using lowercase ASCII letters, digits, and hyphens. `key_id` follows the catalogue format. `revision` is an integer from 1 through 9007199254740991. Binary fields use canonical padded standard Base64 without whitespace. Authenticate all six header fields using their JCS representation.

The caller supplies the expected `key_id` and allowed root generation independently of the record. Validate them before querying the token. Reject unknown formats, missing/extra/duplicate fields, invalid types/encodings/lengths, and authentication failures; release plaintext only after successful authentication. The initial helper caps plaintext at 1 MiB, encoded records at 2 MiB, identifiers at 1,024 ASCII characters, and root-generation labels at 64 characters.

### Updates, rotation, and recovery

- Updating or rewrapping a record increments `revision` and generates fresh salt and nonce. The identifier's `r1` suffix tracks the wrapping-context generation separately.
- Changing `r1` to `r2` changes the HMAC response. Every token holding the same golden key can calculate either; revoking a lost token requires replacing that shared key, rewrapping records, and rotating underlying credentials where old records could expose them.
- Authentication does not prevent replay of an older valid record. Track revisions and explicitly select records during recovery under the [rotation policy](rotation-and-rollback.md). Strong rollback enforcement through independently trusted revision or digest state is deferred to [future improvements](../future.md).
- Preserve the root generation, exact identifier, encrypted record, and any trusted freshness metadata needed for each retained disk or backup. HMAC cannot reconstruct externally issued credentials or OpenBao-generated material. Independent-access requirements belong in [backup-and-restore.md](../backup-and-restore.md#independent-recovery-material).
- Keep responses and derived keys within their authorized memory-only lifetime. KMS expiry must discard both, including copies that could recreate wrapping authority.

The initial helper uses Python `cryptography`'s HKDF and AESGCM APIs. Its validated header contains only restricted ASCII strings and integers within the exact JSON range, so sorted compact JSON provides RFC 8785 canonicalization for this schema. Package pins and offline installation belong to homelab-hsm; [step 00](../installation/00-yubikey-setup.md) documents their use. Before production use, verify disposable test vectors, matching behavior across all four tokens and the software fallback, malformed/tampered records, identifier substitution, rotation, and memory handling. Never use or publish real golden-key responses as test vectors.

Challenge-response needs helper logic; it is not native ZFS unlock integration or an OpenBao seal mechanism. OpenPGP and PKCS#11 are outside the chosen foundation.

## Trust and runtime secret delivery

[Trust's independent bootstrap](../clusters.md#trust) requires manual secret supply. Manual disk unlock and OpenBao unseal are acceptable during operator-controlled startup.

Application/service secrets are fetched from OpenBao; dependent clusters use External Secrets Operator where applicable. A helper on the workstation queries a YubiKey with touch, derives the wrapping key, unwraps the required unseal material, and unseals OpenBao entirely in memory. This is operator-driven unseal, not native YubiKey auto-unseal. The wrapping format is defined above; helper integration and delivery into Talos, scripts, and OpenTofu remain TBD. Wrapped credential records are stored under the [encrypted-record storage policy](encrypted-record-storage.md).

Touch is required when querying a token, not for each scheduled backup. Runtime credentials may be provisioned at setup and held securely server-side; backup-job authentication and lifecycle belong in [backup-and-restore.md](../backup-and-restore.md#openbao-online-backups).

## Trust administration credentials

The wrapped Talos bootstrap bundle is the durable Talos recovery authority.
Recover it with YubiKey authorization and issue fresh client credentials from
the existing Talos CA; do not create a separately wrapped `talosconfig` record
or implicitly replace the cluster identity. Routine Talos administration targets
`os:admin` credentials valid for **24 hours**, held only for the operation in
protected memory. Reissuance does not revoke previously issued credentials.

**Pinned-tool findings:** `talosctl gen config --with-secrets` supports offline
administration credential recovery, but its generated client certificates use
the native one-year default and offer no TTL flag. These are not the selected
routine credential policy. The native `gen csr` / `gen crt --hours 24` path
supports offline signing with the existing Talos CA. Conversely,
`config new --crt-ttl 24h` calls a running node's API; it cannot provide
independent offline recovery.

The CSR/signing commands require named key/certificate paths and write named
outputs. The protected issuer now uses an opened tmpfs directory verified through its
mount ID, an operator-owned 0700 workspace and inherited directory descriptors.
Native child home/temp paths remain in that workspace, with umask 077, a 1 MiB
per-file limit and a seven-file private regular-file allowlist checked after each
command. Approved OS paging, dump suppression and handled-failure cleanup
remain required. SIGKILL/crashes can leave private RAM files; printed workspace
paths support manual cleanup. Never substitute an ordinary temporary directory. The existing sealed-descriptor configuration rehearsal
does not implement this named-file workflow or demonstrate 24-hour issuance.

The native CSR/signing path was smoke-tested with fixed public dummy CA/client
keys on 2026-11-08: issuer signature, client key match, `os:admin`, client-auth
usage and approximately 24-hour expiry all passed. These CLI properties were
also checked against the pinned upstream implementation. The protected named-file rehearsal is implemented with a disposable native
Talos CA and included in offline tmpfs CI. The operator verified the disposable
rehearsal on 2026-11-08; see the
[verification record](../installation/02-trust.md#protected-24-hour-client-issuer).
The [wrapped recovery rehearsal](../../clusters/trust/README.md#wrapped-recovery-rehearsal)
now integrates disposable bundle recovery, native machine validation and fresh
24-hour clients with authority continuity checks. CI uses real record cryptography
and a public fake responder. The operator also verified the complete disposable
flow with the physical YubiKey on 2026-11-08; see the
[verification record](../installation/02-trust.md#wrapped-recovery-and-reissuance-rehearsal).
The [administration inspection wrapper](../../clusters/trust/README.md#administration-client-inspection)
now provides a guarded existing-record entry point and a disposable rehearsal.
It prints only public metadata, requires the initialized private repository for
production recovery, and never initializes a missing identity. The operator
verified the disposable wrapper with the physical YubiKey on 2026-11-08; see the
[verification record](../installation/02-trust.md#operating-entry-points-point-5).
Production bundle use and live-node authentication remain pending. See [native signing](https://github.com/siderolabs/talos/blob/v1.14.5/cmd/talosctl/cmd/mgmt/gen/crt.go)
and [online client issuance](https://github.com/siderolabs/talos/blob/v1.14.5/cmd/talosctl/cmd/talos/config.go).
Kubernetes administration credential retrieval/lifetimes remain a separate
decision after bootstrap; the Talos policy does not set Kubernetes lifetimes.

## Disk encryption and OpenTofu

- **All ZFS storage:** require encryption, including Piraeus backing storage and manual pools. Native ZFS encryption needs dataset/zvol coverage and inheritance checks; it does not encrypt all pool metadata. Layer and provisioning sequence are TBD.
- **OS disks:** All clusters target Talos KMS-backed LUKS2 encryption for sensitive system volumes, including `STATE` and `EPHEMERAL`. Trust uses the independent [coordinator KMS](#trust-bootstrap-kms); Backup, Pi, and Metal use the [OpenBao-backed adapter](#talos-kms-adapter). This does not encrypt every boot partition. Validate volume coverage and compatibility with the assigned OS disks/MD RAID1 on each platform.
- **Manual pools:** preparation and migration must preserve the [manual-storage boundary](../layout.md#provisioning-and-storage-ownership).
- **OpenTofu:** encrypted remote state is allowed. Secret-bearing state, plans, provider output, and failure-recovery files must stay off workstation disk. Backend, locking, key delivery, and provider behavior are TBD; state ownership belongs in [layout.md](../layout.md#common-cluster-layout).
- **Bootstrap:** Trust's state backend and unlock services must work before its protected storage or OpenBao is available.

## Trust bootstrap KMS

**Decision:** Run a dedicated Python gRPC Talos KMS service on the [Trust/Backup UPS coordinator](../inventory.md#shared-infrastructure), serving Trust only. It must work without OpenBao or a Kubernetes cluster and operate independently of the workstation after [SSH authorization](coordinator-sessions.md). UPS shutdown management remains operational while KMS is locked.

- Wrap a random 32-byte KMS key per Trust node using the [v1 wrapping format](#challenges-derivation-and-wrapped-credentials). The [two-layer KMS design](helper-implementation.md#trust-kms-two-layers) uses that key to protect Talos unlock material in a separate `homelab-kms-v1` envelope retained in LUKS metadata. Exact envelope specification, node mappings, and gRPC integration remain pending.
- Authorize a one-hour KMS boot window from the workstation over SSH using the repository-owned shared SSH key loaded into the workstation agent and the `administrator` account. The YubiKey stays in the laptop; delivery, expiry, and operator controls belong in [coordinator sessions](coordinator-sessions.md).
- Serve TLS with a publicly trusted certificate, renewed through DNS-01 on the coordinator independently of Trust's cert-manager/OpenBao. No private CA or custom Talos build is planned for KMS trust.
- Persist DNS API, TLS private-key, and ACME account/bootstrap secrets only as authenticated encrypted payloads under separate YubiKey-derived contexts. The workstation unwraps them after touch and supplies plaintext over SSH for coordinator process-memory use under the [session policy](coordinator-sessions.md). ACME integration and renewal/storage behavior require validation.
- Coordinator and Trust use the same public NTP service. Working Internet/time service is an accepted cold-start dependency; no RTC is required. Configure Trust's networking, DNS, and NTP before encrypted `STATE` loads, using boot-level settings. Establish usable time before TLS-dependent operations; endpoints and cold-boot synchronization/KMS retry tests are TBD.
- **Trusted-network boundary:** TLS authenticates the coordinator to Trust. The stock Talos KMS client does not present client credentials; request UUIDs are identifiers, not authentication. The trusted network is accepted as the client admission boundary. Make an effort to secure communication between these hosts; additional network restrictions/hardening are **TBD exactly how**. Fail closed on locked state, expiry, or unwrap errors.

Startup is **coordinator/time readiness → YubiKey-authorized KMS session → Trust system-volume unlock → manual ZFS unlock and workstation/YubiKey OpenBao unseal → transit/KMS readiness → dependent clusters**. Starting hosts remains operator-controlled.

Independent coordinator-loss recovery remains TBD in [backup-and-restore.md](../backup-and-restore.md#independent-recovery-material). The [temporary OpenBao container recovery path](../backup-and-restore.md#required-recovery-targets) bypasses the coordinator to recover OpenBao access; it does not by itself restore Trust's Talos unlock service.

## Talos KMS adapter

**Decision:** Implement a small Python service using the [Talos KMS protocol](https://github.com/siderolabs/kms-client/blob/main/api/kms/kms.proto), with OpenBao's transit engine performing the cryptography. The protocol is **gRPC**, with `Seal` and `Unseal` RPCs, not a plain HTTP/JSON web API.

- `Seal`: pass the Talos-generated unlock material to transit `encrypt`; return its ciphertext in the protocol's response bytes.
- `Unseal`: pass the stored ciphertext to transit `decrypt`; return the decoded unlock material. Preserve a versioned payload format and the necessary transit key versions.
- Use TLS and scoped transit permissions. Node UUIDs in requests are identifiers, not proof of identity; client authorization compatible with Talos remains TBD. Fail closed on backend or decryption errors.

Planned placement is Trust, beside OpenBao, so the adapter is available before dependent nodes boot. Its credentials and TLS configuration must bootstrap without those nodes. Startup follows the [coordinator-first sequence](#trust-bootstrap-kms), then **OpenBao unseal → transit/KMS readiness → Backup, Pi, and Metal**. Nodes need KMS access again when unlocking after a reboot; touch is required for OpenBao unseal, not each KMS request.

For encrypted `STATE`, networking must work before the machine configuration can be read, and custom CA certificates stored in `STATE` cannot establish KMS trust. Settle early-boot addressing/DNS and a Talos-supported TLS trust path before rollout. Adapter packaging, endpoint, authentication, timeouts, key mapping/rotation, and restore tests remain TBD; do not copy the reference test server's random-data fallback behavior.

## YubiKey configuration runbook

[00 - YubiKey setup](../installation/00-yubikey-setup.md) uses the level1vault live OS and separately imported homelab-hsm checkout. HSM commands install from committed wheels offline; level1vault owns pass storage/retrieval and homelab-hsm owns generation/programming/verification. Initial physical-token and replica-retrieval acceptance is complete; see step 00. Replacement/loss and rotation requirements belong in [recovery procedures](recovery-procedures.md) and [rotation and rollback](rotation-and-rollback.md).

## Remaining decisions

Approved topic decisions and remaining implementation work:

- [Encrypted-record storage](encrypted-record-storage.md) — decision approved; implementation pending.
- [YubiKey setup](yubikey-setup.md) — configured and physically verified on all four tokens.
- [Yubico CLI fallback](yubico-fallback.md) — manually verify, debug, and sanity-check our Python implementation with Ubuntu-packaged Yubico tools; reference only, not selected or hardware-tested.
- [Golden-key custody](golden-key-custody.md) — initial generation custody, replication and independent replica retrieval verified.
- [OpenBao unseal](openbao-unseal.md) — unseal decision approved; implementation, recovery administration, and restore verification pending.
- [Credential catalogue](yubikey.md#record-and-maintenance-requirements) — catalogue rules approved; production entries and consumer integrations pending.
- [Coordinator sessions](coordinator-sessions.md) — decision approved; implementation and verification pending.
- [Helper implementation](helper-implementation.md) — initial token/wrapping helpers physically verified; service helpers pending.
- [Rotation and rollback](rotation-and-rollback.md) — decision approved; procedures and verification pending. Strong rollback enforcement deferred.
- [Recovery procedures](recovery-procedures.md) — recovery requirements approved; commands and drills pending.

Existing decisions remain in this document and the [YubiKey catalogue](yubikey.md).

## Upstream references

- [HKDF (RFC 5869)](https://www.rfc-editor.org/rfc/rfc5869).
- [JSON canonicalization (RFC 8785)](https://www.rfc-editor.org/rfc/rfc8785).
- [Python cryptography HKDF](https://cryptography.io/en/stable/hazmat/primitives/key-derivation-functions/#hkdf) and [AESGCM](https://cryptography.io/en/stable/hazmat/primitives/aead/#cryptography.hazmat.primitives.ciphers.aead.AESGCM).
- [Yubico challenge-response](https://docs.yubico.com/yesdk/users-manual/application-otp/challenge-response.html).
- [YubiKey Manager OTP implementation](https://github.com/Yubico/yubikey-manager/blob/5.9.2/yubikit/yubiotp.py), including legacy firmware support and fixed-length configuration.
- [Talos disk encryption](https://docs.siderolabs.com/talos/v1.14/configure-your-talos-cluster/storage-and-disk-management/disk-encryption).
- [OpenZFS encryption](https://openzfs.github.io/openzfs-docs/man/master/8/zfs-load-key.8.html#encryption).
- [OpenTofu state/plan encryption](https://opentofu.org/docs/language/state/encryption/).
- [Kubernetes Secrets](https://kubernetes.io/docs/concepts/configuration/secret/).
- [OpenBao security model](https://openbao.org/docs/internals/security/).
- [Talos KMS reference implementation](https://github.com/siderolabs/kms-client).
- [Talos v1.14.2 KMS client and TLS behavior](https://github.com/siderolabs/talos/blob/v1.14.2/internal/pkg/encryption/keys/kms.go).
- [Talos preboot networking/DNS/NTP kernel parameters](https://github.com/siderolabs/talos/blob/v1.14.2/website/content/v1.14/reference/kernel.md).
- [OpenBao transit API](https://openbao.org/docs/api/secret/transit/).


## Coordinator host hardening

All three UPS coordinators use the [shared hardening policy](coordinator-hardening.md): restricted SSH/nftables access, automatic security updates without automatic reboots, and memory/service protections. The role is implemented; deployment and hardware verification remain pending. KMS-specific service and network restrictions remain part of its setup.

## Coordinator local account passwords

Each coordinator has an independently random `administrator` password, wrapped
with the existing YubiKey foundation and owned by this repository. The
[catalogue](yubikey.md#implemented-coordinator-passwords) owns identifiers; the
[runbook](../../runbooks/coordinator-passwords.md) owns creation and delivery.
SSH remains key-only with the repository-owned shared key and passwordless sudo.
Only explicit recovery reveal displays plaintext; normal creation and delivery
do not. Real credential generation and Pi verification remain pending.

## Coordinator SSH identity

The three coordinators share one randomly generated, passphrase-less Ed25519
private key, persisted only as a YubiKey-wrapped record in the private `homelab-secrets` submodule and
recovery clones. Its public key is committed normally. Unwrap directly into the
local workstation OpenSSH agent for a one-hour lifetime before management
operations; never write a plaintext private-key file or forward the agent.
Agent memory remains within the workstation secret-handling boundary.
The [catalogue](yubikey.md#implemented-coordinator-ssh-identity) owns the lookup;
the [SSH key runbook](../../runbooks/coordinator-ssh-key.md) owns setup, migration,
loading and removal. Implementation is present; production generation and
hardware verification remain pending.
