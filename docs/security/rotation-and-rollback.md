# Rotation and rollback

**Decision approved; procedures and verification pending.**

## Token replacement and compromise

A failed token still in the operator's possession may be replaced using
the existing golden key from [Level 1](golden-key-custody.md).
Program and verify the replacement under the [setup policy](yubikey-setup.md).

Treat a lost or potentially compromised token as exposure of the shared
foundation. Replace the golden key, rewrap records, and rotate underlying
credentials that exposed historical records could reveal. Changing lookup
identifiers alone cannot revoke a token holding the old golden key.

## Golden-key migration

Establish the new generation in Level 1. Rewrap credentials in memory
under that generation, increment record revisions, and use fresh salt
and nonce under the [record rules](security.md#updates-rotation-and-recovery).

Verify new records and recovery copies before retiring old material.
Migrate tokens one at a time, preserving a verified recovery path.
During migration, record each token's generation and verification status;
tokens on different generations are not interchangeable.

Refresh coordinator records. Exact migration
commands and completion checks remain pending.

## Node KMS-key rotation

Rewrapping a node KMS key under a new golden key preserves its value and
disk compatibility. Replacing the actual node KMS key requires migrating
disk payloads to the new KMS-key generation under the
[two-layer design](helper-implementation.md#vault-kms-two-layers).
Verify unlock and recovery before retiring the previous key.

## Retention and exposure

Retain older generations while surviving disks or retained backups
require them. Track these dependencies in the catalogue and keep required
golden-key generations in Level 1.

Git history and existing clones retain old ciphertext. Rewrapping does
not erase exposure through those copies, and rotation cannot make an
already exposed historical backup confidential again.

## Rollback

Track record revisions and explicitly select the required generations
and records during recovery. Authentication proves record integrity,
not freshness: an older authentic record may still decrypt.

Strong enforcement against malicious rollback requires independently
trusted revision or digest state and is deferred to
[future improvements](../future.md). Initial tooling does not claim
cryptographic rollback protection.

## Remaining implementation work

Write and test token replacement, golden-key migration, credential
rotation, node KMS-payload migration, and retirement procedures.
Record non-secret migration results and recovery dependencies.
