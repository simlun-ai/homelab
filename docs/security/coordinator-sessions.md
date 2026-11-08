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
Keep secret payloads out of command arguments, files, and logs.
Follow the [memory-only handling policy](security.md#secret-handling-boundary)
on both hosts.

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
implementation remain pending. Verify disconnect, expiry, lock,
restart, and certificate-renewal behavior.

The [two-layer KMS design](helper-implementation.md#trust-kms-two-layers)
uses YubiKey-wrapped node KMS keys to support fresh Seal payloads and
existing Unseal payloads. Exact envelope and delivery specifications
are proposed in the [draft contract](trust-bootstrap-kms.md), pending review;
do not give the coordinator raw HMAC responses or
indefinite KMS authority.

