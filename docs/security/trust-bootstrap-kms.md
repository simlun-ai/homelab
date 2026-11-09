# Trust bootstrap KMS contract

**Design walkthrough approved — 2026-11-08; implementation and verification
pending. No service, keys or endpoint deployment is implemented by this document.** Existing approved policy remains authoritative
in [security.md](security.md#trust-bootstrap-kms) and
[coordinator sessions](coordinator-sessions.md). The envelope codec and in-process session model are now implemented and
software-tested as described below. The loopback rehearsal implements gRPC error
mapping. Local authorization framing and daemon/process isolation remain proposed.
This contract covers Trust only; the OpenBao transit adapter is separate.

## Walkthrough decisions (2026-11-08)

The operator approved the following behavior and implementation sequence. The
envelope encoding and in-process bounds are selected and tested in the software
core below; transport framing and worker mechanics remain proposals.

1. One wrapped KMS key per node protects independent Talos unlock payloads with
   fresh randomness and authenticated node/generation binding. Missing keys or
   damaged/unknown envelopes fail without replacement-key generation. Authorization
   lasts one hour, independent of SSH disconnection and request traffic. Lock,
   expiry or restart removes authority; opening a replacement window requires
   explicit lock and fresh touch. Discard results completing after lock/expiry.
2. Use `https://kms.k8s-aux.simlun.se:443`, gRPC over TLS on TCP 443, with internal
   DNS mapping to `10.10.0.5` and a public certificate issued using Cloudflare
   DNS-01. Selection does not establish DNS, certificate or listener deployment.
3. Implement software-only envelope/session tests first, using disposable public
   keys and controlled clocks in CI; test tampering, wrong-node/generation use,
   expiry, locking, activation retries and interrupted acknowledgments.
4. Split the non-destructive Pi live-boot experiment into hardware discovery
   (stable UUID, Ethernet, network/time and disk identities) and KMS connectivity
   once a test service exists. Live-environment networking alone does not verify
   pre-STATE readiness. No disk formatting or installation in this experiment.
5. Deploy the locked service with Ansible, establish TLS, restrict network access,
   verify YubiKey-authorized lifecycle/failure behavior, then rehearse coordinator
   replacement against an existing disposable payload. Agree independent recovery
   copies/locations before production KMS key generation. Encrypted installation
   follows successful service, Pi connectivity and recovery checks.

## Existing decisions and dependencies

| Boundary | Approved requirement |
| --- | --- |
| Placement | Python gRPC service on `ups-aux` (`10.10.0.5`), independent of Trust/OpenBao. UPS management remains available while KMS is locked. |
| Authority | Random 32-byte KMS key per Trust node, wrapped as `homelab-wrap-v1`. This is separate from the Talos bootstrap CA bundle. |
| Authorization | Workstation YubiKey touch; verified SSH to `administrator`; plaintext streamed to a restricted local daemon socket. Never send golden-key material or raw HMAC responses. |
| Lifetime | One-hour KMS window, starting at successful activation; traffic does not extend it. DNS/TLS/ACME credentials have separate process lifetimes. |
| Payload protection | Fresh salt and nonce per Seal, HKDF-SHA-256, AES-256-GCM; authenticated `homelab-kms-v1` envelope retained by Talos in LUKS metadata. |
| Network trust | Server-authenticated TLS with a public certificate. The trusted network is the client-admission boundary; UUIDs are not credentials. |
| Cold start | Independent networking, DNS and public NTP before TLS and encrypted STATE unlock; Internet/time are accepted dependencies. |
| Recovery | Preserve existing node KMS keys and generations; never replace a missing key automatically. Coordinator-loss procedure remains unverified. |

## Pinned Talos interface

Inspected Talos `v1.14.5`, which depends on `kms-client v0.2.0`:

- `sidero.kms.KMSService` has unary `Seal` and `Unseal` RPCs.
- Both accept `Request { string node_uuid = 1; bytes data = 2; }` and return
  `Response { bytes data = 1; }`. There is no volume ID or authentication field.
- During new key creation Talos generates 32 random bytes and sends those bytes
  to Seal. It stores the returned opaque bytes as `sealedData` in its LUKS token.
- During unlock it sends that stored value to Unseal. Talos Base64-encodes the
  returned raw unlock bytes when constructing the LUKS key. The service must
  return the original 32 bytes, not a Base64 string or a new random value.
- Each inspected NewKey/GetKey operation has a ten-second context timeout.
  This does not establish overall boot retry behavior; test that on the Pi.
- The client configures server TLS trust through Talos's root store and supplies
  no client certificate. Endpoint parsing defaults a bare address to `grpc://`,
  which is insecure. Require an explicit `https://<certificate-name>:<port>`
  endpoint for the planned gRPC-over-TLS service; do not use a bare address.

Sources: [Talos dependency](https://github.com/siderolabs/talos/blob/v1.14.5/go.mod),
[client and LUKS token handling](https://github.com/siderolabs/talos/blob/v1.14.5/internal/pkg/encryption/keys/kms.go),
[endpoint parser](https://github.com/siderolabs/talos/blob/v1.14.5/internal/pkg/endpoint/endpoint.go),
[protocol](https://github.com/siderolabs/kms-client/blob/v0.2.0/api/kms/kms.proto).
Recheck these sources when the Trust Talos pin changes.

## Proposed node registration and records

Register `trust-cp1` with an independently recorded hardware UUID observed through
pinned Talos on the actual Pi. Live discovery on 2026-11-09 reported
`00d03115-0000-0000-1000-000089261f6e`; see the
[inventory](../inventory.md#trust) and [baseline record](../installation/02-trust.md#read-only-live-baseline-2026-11-09).
This is an observed candidate, not an operational registration. The UUID remained
unchanged across the recorded cold boot after disabling the UEFI RAM cap on
2026-11-09. Stability across other firmware changes, reinstall and the intended
disk layout still needs verification before relying on it for recovery. Do not infer a UUID from the
hostname, IP, MAC or Raspberry Pi serial.

Proposed wrapped key context: `homelab/v1/trust/kms/trust-cp1/r1`, under the
catalogue's existing `trust/kms/<node-id>/r1` reservation. Final context, filename,
UUID and generation mapping need review together. Do not add an operational
manifest entry or generate a production record until that mapping is approved.

Non-secret coordinator configuration maps a canonical UUID to explicitly allowed
key IDs and one active Seal generation. Parse UUID text to canonical lowercase
hyphenated form; reject malformed or nil UUIDs. Normalize the request UUID before
lookup and envelope comparison. Do not treat UUID knowledge as proof of origin.
No default node, first-match key, remote key fetch, or fallback generation.

Ciphertext deployment follows [encrypted-record storage](encrypted-record-storage.md#coordinator-deployment).
Keep the selected configuration and records locally; boot must not fetch GitHub.
Unseal selects only the exact configured generation named by its envelope.
Retain older generations while surviving disks or retained recovery material
need them; authorization must explicitly include any such generation.

## `homelab-kms-v1` envelope

Response `data` from Seal is UTF-8 JSON with exactly these seven fields:

| Field | Type and validation |
| --- | --- |
| `format` | String, exactly `homelab-kms-v1`. |
| `node_uuid` | Canonical registered UUID, equal to the normalized request UUID. |
| `key_id` | Exact allowed full wrapped-key context, identifying its generation. |
| `salt` | Canonical standard Base64 of 32 fresh random bytes. |
| `nonce` | Canonical standard Base64 of 12 fresh random bytes. |
| `ciphertext` | Canonical standard Base64 of 32 ciphertext bytes plus the 16-byte GCM tag. |
| `encoding` | String, exactly `raw-32`, documenting the pinned client's input size. |

Implemented derivation: HKDF-SHA-256 with length 32, the unwrapped node KMS key as
input key material, the decoded salt, and info equal to the ASCII encodings of
`homelab-kms-v1`, canonical UUID and full key ID joined by single NUL bytes.
The six fields other than `ciphertext` are the authenticated header. Encode that
header as sorted-key, compact, ASCII JSON with no whitespace for AES-GCM AAD;
all permitted values are strings in restricted ASCII alphabets. The fixed public
vector in `tests/kms_vector.py` covers the HKDF input/output, AAD and full envelope;
it was computed separately using stdlib HMAC and PyCryptodome 3.23.0 AES-GCM,
then checked against the runtime cryptography implementation. PyCryptodome is
not a runtime or CI dependency. Key IDs are limited to 256 ASCII characters
and the `homelab/v1/trust/kms/<node-id>/r<generation>` namespace.
Outer JSON whitespace does not change the reconstructed AAD. Authentication
does not prevent replay of an older valid envelope; the existing
[rotation/rollback policy](rotation-and-rollback.md) still applies.

Seal accepts exactly 32 raw bytes, encrypts them and returns the envelope.
Unseal validates size, unique field names, exact field set, string types,
canonical Base64, format, encoding, node and allowed key generation before
performing decryption. Reject aliases, extra fields, trailing JSON data,
invalid tags and plaintext of any length other than 32. Never fall back to
`homelab-wrap-v1`, another node, another generation, or generated plaintext.

Implemented bound: 4 KiB for envelope data, checked before JSON decoding.
The loopback transport enforces an 8 KiB gRPC message limit. Local authorization
framing and transport time budgets still need implementation and Pi 3
measurement within Talos's ten-second operation timeout. Do not log request,
response, envelope or decrypted payload bytes. Errors expose only static codes.

## Proposed local authorization protocol and process boundary

Keep status, activation and lock off the network KMS API. Use a fixed coordinator
SSH command backed by a Unix stream socket owned by the service, with a dedicated
authorized local group, mode `0660`, and a protected parent directory. Exact
command path, socket path, account/group and systemd units are **TBD**. Validate
peer UID/group on the socket; a network caller cannot activate a session.

Proposal: one length-prefixed UTF-8 JSON request per connection, four-byte
unsigned big-endian length, maximum 16 KiB; reject duplicate/unknown fields and
incomplete or oversized frames. An SSH invocation uses only a public action in
arguments; all key material travels on stdin. No shell evaluation or secret
arguments, environment variables, named files, or echoed payloads.

- `status`: returns protocol version, daemon instance ID, TLS/time readiness,
  KMS state, authorized public key IDs, session ID and remaining seconds only.
- `open-boot-window`: includes protocol version, expected daemon instance ID,
  fresh request ID, and a bounded list of UUID/key-ID/raw-key entries. Keys are
  canonical Base64 of exactly 32 bytes. Validate the entire batch against local
  mappings before atomic activation; no partial admission. Acknowledgment returns
  public session ID, accepted IDs and lifetime after activation succeeds.
- `lock-KMS`: invalidates the session and pending operations; acknowledgment
  means its worker has exited and further KMS release is blocked.

Workstation expected identifiers/root generations come from independently
selected local configuration, not solely the manifest offered by the remote
host. TLS/DNS/ACME secret delivery is a separately validated action with its own
schema; it cannot implicitly open a KMS window. Its payload details are **TBD**.

Propose rejecting activation while a session is active. To replace one, explicitly
lock and authorize again with fresh touch. Repeating an activation after a lost
acknowledgment must not reset a timer: query status using request/session IDs,
then explicitly lock if uncertain. Daemon restart changes its instance ID and
cannot revive an old activation. Session protocol is not a defense against a
compromised authorized administrator or coordinator root account.

Propose a disposable KMS worker holding node keys only for one boot window;
the parent retains process-lifetime TLS/DNS/ACME credentials separately. Terminate
the worker at lock, expiry or restart, cancel in-flight RPCs, and invalidate its
session epoch. Gate admission and response release against the live epoch and
deadline; a result completing after lock/expiry is discarded. Bytes already
released before locking cannot be recalled. Start with no active worker or keys.

Use a monotonic elapsed-time source for the hour, including suspend time (Linux
`CLOCK_BOOTTIME` selected for the software core); wall-clock corrections must
not extend authorization. Daemon scheduling and worker termination are pending.
Never restart a worker with cached keys after failure. No plaintext key or unlock
cache survives a window. Python object deletion is not secure zeroization;
process isolation, dump/paging protection and observed cleanup remain validation
requirements. UPS processes must not share the KMS worker's lifetime.

## Proposed readiness, TLS and admission behavior

| Condition | Required behavior |
| --- | --- |
| Coordinator cold start | UPS and SSH/status available independently. KMS locked. Restore local ciphertext/configuration and verify time/network readiness. |
| TLS material absent or certificate invalid | No plaintext listener or verification bypass. Authorize service secrets over independently verified SSH, obtain/renew a public certificate, then expose TLS. |
| TLS ready, KMS locked/expired | TLS/status may remain available; Seal and Unseal return `FAILED_PRECONDITION` without secret output. |
| Unknown/unapproved UUID or key generation | `PERMISSION_DENIED`; no key generation or alternative-key search. |
| Malformed frame/envelope, wrong input size or invalid tag | Static `INVALID_ARGUMENT`; no parser/decryption details. |
| Capacity exhausted or worker unavailable | `RESOURCE_EXHAUSTED` or `UNAVAILABLE`; bounded failure, no plaintext fallback. |
| SSH disconnect after acknowledged activation | Window continues to its original deadline; workstation/token may disconnect. |
| Lock, expiry, worker/daemon restart, coordinator power loss | Pending operations invalidated; fresh workstation/YubiKey authorization required. Already unlocked volumes keep running. |
| Trust reboots after expiry | Unlock cannot succeed until a fresh window is authorized with the same retained node key. |

Use `kms.k8s-aux.simlun.se`, resolving internally to `10.10.0.5`, with a matching
SAN/full certificate chain; serve gRPC over TLS on TCP 443. Cloudflare DNS-01
is selected for certificate issuance. DNS and certificate deployment are pending;
see the [required DNS entries](../network.md#required-dns-entries).
**Exact Cloudflare zone/delegation and credential scope, ACME client and
renewal/key-persistence policy remain TBD.** Initial and
expired-certificate recovery must use SSH and independent DNS/ACME access;
existing KMS TLS cannot be their only prerequisite. A renewed certificate may
reuse an already protected private key if supported; persisting a new key needs
fresh YubiKey wrapping. Do not add an unencrypted ACME client key cache.

Bind only the selected coordinator address/port. Propose coordinator nftables
admission from `trust-cp1`'s address, with inter-VLAN gateway restrictions as
additional containment. Both hosts are on VLAN 10, so router rules alone cannot
isolate same-VLAN peers. UUID and source IP checks do not prevent an attacker
already inside the trusted network from impersonating a node. Exact switch,
gateway and host rules, service-user restrictions, and their tests remain TBD.

Choose the same public NTP service for coordinator and Trust, with working
pre-STATE addressing, DNS and time synchronization. Exact boot-level mechanism,
NTP endpoints and observed retry/order behavior require a Pi live-boot test.
The committed machine-network patch alone does not prove pre-STATE readiness.

## Independent coordinator-loss recovery gate

Proposal: rebuild a clean coordinator from the parent configuration, offline
helper packages and independently available private wrapped records; verify the
replacement SSH host identity independently, restore or reissue KMS TLS using
DNS-01, and authorize the **same** registered node key/generations with the
workstation YubiKey (or separately tested software recovery). Surviving LUKS
metadata must still contain the corresponding sealed payloads. A new node key
or a fresh Talos bootstrap bundle cannot recover a lost KMS key.

The [backup owner](../backup-and-restore.md#independent-recovery-material) must
settle independent record/configuration/package copies, access credentials,
locations, UUID-change handling, LUKS-header recovery requirements, and the exact
replacement-host procedure. This draft does not create a backup medium or claim
that coordinator-loss recovery works. Verify loss of coordinator and expired TLS
without OpenBao, unlocked Trust storage, or plaintext workstation-disk files
before declaring the encrypted installation recoverable.

## Implemented software core and its limits

`/scripts/homelab/trust_kms/` contains the envelope codec and thread-safe session
state machine. Existing homelab-hsm wrapping remains responsible for stored node
keys; its library is exercised with a public fake responder in an integration
test. No shared wrapping format or HSM submodule pin changes.

Run the offline helper tests (including the KMS cases) after normal installation:

```sh
make -C support/hsm tools
make -C support/hsm test
```

The existing `helpers` CI target discovers these tests automatically, alongside
parent lint and strict type checking. Fixed vectors, malformed input/tampering,
independent payloads, explicit generation admission, atomic activation, lost
acknowledgment/status lookup, expiry/lock/restart and late-result races use only
public disposable keys and controlled clocks. There are no real-hour sleeps.

The operator also verified `make -C support/hsm test` on `simlun-x1` on
2026-11-08; the complete target passed, including the final 74-test HSM suite.
See the [workstation verification record](../installation/02-trust.md#kms-software-core).
This is software-test evidence; the integration limits below still apply.

Session limits: 16 registered nodes, 8 configured generations per node, 64 grants
per activation, 8 in-flight operations and 1024 accepted activation request IDs
per daemon instance. IDs remain remembered after expiry/lock, so replay cannot
reopen a window. Hitting the request-ID bound rejects activation until an explicit
restart changes the daemon instance; it does not evict IDs and enable replay.
Unknown configured-but-unloaded generations are denied without searching other
keys. Clock failure, non-finite values or regression clears retained authority.

**This is not a deployable service or secure worker implementation.** The core
API trusts its local caller; it does not authenticate peers or enforce YubiKey
touch. It validates the current deadline at status, activation, expiry and RPC
entry/release boundaries using Linux `CLOCK_BOOTTIME` by default. A future daemon
must schedule `expire()` at the deadline even without traffic, terminate its
key-holding worker, bound/cancel transport work and gate the final network
response handoff against the session epoch/deadline. Returning bytes from the
core is only the tested in-process release boundary.

Clearing dictionaries drops the model's retained key references; caller-owned
keys and in-flight crypto copies may still exist until their owners release
them. Python does not promise physical erasure. No process memory isolation,
unattended expiry scheduler, socket framing, gRPC/TLS listener, SSH command,
Ansible deployment, production UUID/key registration or hardware verification
is supplied by this slice. Those gates remain mandatory before live keys.

## Acceptance criteria before encrypted installation

| Test layer | Required evidence and status |
| --- | --- |
| Protocol/crypto unit tests | Software tests pass for the fixed public vector; exact 32-byte round trip; fresh salt/nonce; unknown/duplicate/oversized fields, wrong UUID/generation, malformed encodings and every authenticated-field/ciphertext mutation rejected. |
| Session tests with controlled clocks | In-process tests pass for atomic batches, stale daemon ID and repeated activation rejected; dropped acknowledgment resolved without extension; wall-clock changes and suspend do not extend the modeled hour. Local peer admission remains pending. |
| Concurrency/failure tests | In-process race tests pass for discarding late results; actual worker termination and network release gating remain pending: worker crash/restart clears authority; bounded request queues; no secret logs, dumps or named disk files. |
| Native client integration | Generated Python stubs match pinned proto; real gRPC/TLS interoperability, wrong hostname/chain/expiry rejected, no client-auth assumption; repeated Seal/Unseal for independent STATE/EPHEMERAL payloads under one node key. |
| Coordinator deployment | SSH and UPS available while locked; local ciphertext-only startup; one-hour window, lock, disconnect, reboot, time loss, certificate renewal and expired-certificate recovery tested. |
| Pi live boot | Recorded stable UUID; actual pre-STATE Ethernet/DNS/NTP; TLS chain trusted by stock Talos; cold-boot unlock, timeout/retry behavior and expired-window rejection. |
| Independent recovery | Rebuilt coordinator unseals an existing disposable payload using preserved generations without original coordinator/OpenBao; document real recovery locations and prerequisites. |

Next: review the software-core evidence, then proceed with the agreed
non-destructive Pi live-boot discovery. UUID/time/admission/recovery choices and
the daemon/transport/process-boundary implementation remain prerequisites for
service deployment, production keys and encrypted installation.

## Disposable loopback transport

The [helper rehearsal](../../support/hsm/README.md#trust-kms-loopback-rehearsal)
runs the Talos Seal and Unseal RPCs over verified TLS on a loopback listener.
The harness activates the existing in-process session directly using disposable
inputs and advances a controlled clock to exercise expiry. It checks locked and
expired requests, a successful round trip, request bounds, static error codes,
and certificate trust. The handler checks the session epoch before returning
the encoded response to gRPC.

The operator ran `make -C support/hsm kms-tls-rehearse` successfully on
`simlun-x1` with Python 3.13.18 at `b2ca4e6` on 2026-11-09. See the
[Trust runbook](../installation/02-trust.md#experiment-record-and-acceptance-checks).

This stage uses one process. Production socket authorization, an expiry
scheduler, worker termination, and a production response handoff still require
implementation and verification before coordinator deployment.
