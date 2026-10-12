# Encrypted-record storage

**Decision approved; implementation pending.**

## Authoritative records

Keep `homelab-wrap-v1` encrypted JSON records in the private homelab repository under `secrets/wrapped/`: one file per credential record, with a public manifest mapping exact identifiers to filenames. Manifest schema and helper commands belong to [helper implementation](helper-implementation.md).

Valid wrapped ciphertext may be committed and stored on workstation disk, recovery USBs, and consuming hosts. Golden-key material, HMAC responses, derived keys, and decrypted credentials remain subject to the [memory-only handling policy](security.md#secret-handling-boundary). This exception covers wrapped credential records, not workstation-disk staging of OpenBao snapshots.

Wrap credentials entirely in memory. Verify that each new record decrypts to the original bytes before replacing the current record; write only the authenticated encrypted record. Use the [v1 record and revision rules](security.md#updates-rotation-and-recovery).

## Recovery USB clones

Each YubiKey's paired recovery USB contains a full, non-shallow clone of the homelab Git repository, including checked-out files, local Git history, documentation, helper source, and committed wrapped records. No Git access token or other plaintext credential may be embedded in the clone.

The clone provides wrapped bootstrap/recovery records without GitHub or OpenBao. OpenBao snapshots remain separately backed up to R2. Required tool binaries and dependencies still need the independently obtainable recovery tooling described in [recovery procedures](recovery-procedures.md); source availability alone does not establish offline executability.

Refresh all four clones after recovery-critical record, protocol, helper, or guide changes. Record each clone's commit and verify its integrity and required records. Exact refresh commands and checks remain implementation work.

## Coordinator deployment

Deploy the coordinator's required wrapped KMS, DNS, TLS, and ACME records to its local persistent storage. Startup reads these local records without fetching GitHub or OpenBao.

Ansible provisioning is selected for the coordinator, with implementation tracked in [01 - Main coordinator](../installation/01-main-coordinator.md). It copies the wrapped records from the repository to local storage without decrypting them. Local paths, permissions, and update mechanics remain implementation details. The workstation unwraps runtime credentials and supplies authorization over SSH under the [coordinator session policy](coordinator-sessions.md).

Git history retains old ciphertext. Credential rotation, retention, and trusted rollback detection belong to [rotation and rollback](rotation-and-rollback.md).
