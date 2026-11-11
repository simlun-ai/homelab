# Coordinator sessions

**Decision approved; implementation and verification pending.**

## Workstation authorization

Keep the YubiKey in the workstation laptop. Load the [repository-owned shared SSH key](../../runbooks/coordinator-ssh-key.md)
into the local agent and use the `administrator` account. SSH access and host-key verification must work independently
of Trust and OpenBao.

The coordinator starts with KMS locked; UPS management remains available.

1. The workstation helper connects over SSH with verified host identity
   and retrieves the coordinator's public manifest and wrapped records.
2. Validate identifiers and allowed golden-key generations against
   independently expected values before querying the token.
3. Prompt for touch for each required HMAC operation and prepare the
   authorized material in workstation memory.
4. Stream it through SSH standard input to a coordinator command, which
   passes it to the running daemon through a local Unix socket restricted
   to authorized local users.
5. The daemon acknowledges successful activation. The workstation
   discards its secret material; SSH can disconnect and the token can
   be removed.

Never transmit the golden key or raw HMAC responses to the coordinator.
Keep secret payloads out of command arguments, persistent files, and logs.
Follow the [memory-only handling policy](security.md#secret-handling-boundary)
on both hosts. The operator approved one exception on 2026-11-09 for Certbot
and its Cloudflare plugin on `ups-aux`. Their named secret files may exist
inside a dedicated, access-restricted tmpfs mount verified with `noswap`.
Check coordinator swap and core dump policy before reading credentials.
Remove the workspace when ACME authorization ends. Workstation and KMS
unlock secrets continue to use memory or streams.

## Separate lifetimes

| Material delivered | Lifetime |
| --- | --- |
| Unwrapped random 32-byte KMS keys for explicitly authorized Trust nodes | One-hour boot window. |
| Decrypted DNS API credential, TLS private key, and ACME account secrets | Coordinator process lifetime. |

Start the one-hour window on successful KMS activation, measured by the
coordinator's monotonic clock. Requests and retries do not extend it.
Expiry or explicit locking rejects further KMS operations and discards
all KMS secret material and copies that could recreate unlock authority.
Already unlocked volumes continue running.

Opening a new window requires fresh workstation/YubiKey authorization.
Coordinator restart or power loss discards all supplied secrets and
requires authorization again. SSH disconnection does not end a session.

ACME/TLS ciphertext and archives stay on the coordinator. The workstation
retrieves and unwraps them in memory, then streams the result back over verified
SSH during authorization. The DNS token retains its private-repository recovery
copy. Lost coordinator state is explicitly recreated; it never implicitly
regenerates node KMS keys or Talos authority.

Certificate renewal may use DNS and ACME credentials already in memory.
Wrapping a newly generated private key or updating a secret record
requires fresh token operations; do not retain HMAC responses for
unattended rewrapping.

## Operator controls

Provide status, open-boot-window, and lock-KMS operations. Status reports
readiness and remaining time without secrets. Locking KMS leaves
DNS/TLS/ACME operation and UPS management available.

The [2026-11-08 walkthrough](trust-bootstrap-kms.md#walkthrough-decisions-2026-11-08)
approved explicit lock before replacement authorization and discarding results
that complete after lock/expiry. The window still does not authenticate network
clients; the trusted-network boundary remains in effect.

## Remaining implementation work

Review the [proposed authorization protocol and process boundary](trust-bootstrap-kms.md#proposed-local-authorization-protocol-and-process-boundary),
including framing, atomic activation, acknowledgments, deadline races and worker
termination. Command/socket paths, service identities, TLS-secret delivery and
daemon/transport implementation remain pending. The [software session model](trust-bootstrap-kms.md#implemented-software-core-and-its-limits)
now tests atomic activation, acknowledgment lookup, expiry/lock and restart
semantics with controlled clocks; it is not a scheduler or isolated worker.
Verify actual disconnect, expiry, lock,
restart, and certificate-renewal behavior.

The [two-layer KMS design](helper-implementation.md#trust-kms-two-layers)
uses YubiKey-wrapped node KMS keys to support fresh Seal payloads and
existing Unseal payloads. Exact envelope and delivery specifications
are separated in the [contract](trust-bootstrap-kms.md): envelope encoding is
implemented and tested; local delivery framing remains proposed;
do not give the coordinator raw HMAC responses or
indefinite KMS authority.


## TLS-only listener authorization

The [TLS authorization slice](../installation/01-main-coordinator.md#authorize-and-verify-the-locked-tls-listener)
was deployed and verified on `ups-aux` on 2026-11-11. It recovers the
existing production record, verifies it, and streams only the TLS key/full chain
to the root SSH helper and the restricted `/run/trust-kms/tls.sock`. A captured
daemon instance must still match; TLS must be disabled and KMS locked. The
bounded request schema is separate from `open-boot-window`. It cannot supply
node keys or open KMS authority. Root and the service UID are the only accepted
local peers. Public status reports instance, TLS/KMS state, endpoint and public
certificate fingerprint/expiry, never PEMs.

The service retains TLS material in memory until exit or certificate invalidity.
It disables dumping and checks non-swappable/zram-only coordinator paging
before accepting private keys. It revalidates hostname, key and system trust
using anonymous memory descriptors containing public certificates only.
Certificate expiry or a clock rollback before validity closes the listener.
Restart clears authorization and requires new workstation/YubiKey delivery;
there is no automatic recovery of plaintext or wrapping authority. A lost
activation acknowledgment requires status inspection before retrying. Automatic
renewal/reload and long-lived DNS/ACME authorization integration remain pending.
