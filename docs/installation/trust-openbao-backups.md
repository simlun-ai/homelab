# Trust OpenBao snapshot and restore milestone

Status on 2026-11-21. Planning. The first implementation is a manually
triggered Raft snapshot to Cloudflare R2, followed by an isolated restore on
the operator workstation. HTTPS and YubiKey-backed manual unseal are
[verified on Trust](trust-openbao-network.md). The
[backup and restore design](../backup-and-restore.md#openbao-online-backups)
defines the recovery requirements.

## First implementation

1. Provision a private R2 bucket dedicated to Trust backups. Record the endpoint,
   bucket and object naming convention in the emergency recovery guide. Use a
   unique UTC-based object key for each snapshot. Create separate bucket-scoped
   credentials for the in-cluster uploader and the read-only restore operator.
   Keep the wrapped recovery credential independently available before Trust
   starts.
2. Use the wrapped initial root token in a manual, memory-only workstation
   session to configure a dedicated OpenBao backup identity. Grant it access to
   the Raft snapshot endpoint. Verify that it can take a snapshot and that it
   cannot restore snapshots or administer secrets. Use a short-lived job token.
   Decide how the job obtains that token and how the R2 credential reaches the
   pod using the existing wrapped-record workflow.
3. Choose the snapshot transfer and encryption implementation. Prefer an
   independently recoverable encryption key for the uploaded artifact, with
   encryption before upload and a verified memory-backed staging path if
   needed. Set a size limit and define cleanup, deadlines, and failure
   reporting. Evaluate the pinned upstream snapshot tooling against this flow
   before adding a custom uploader.
4. Run a single backup job in Trust. Record the snapshot identity, OpenBao
   version, object size and integrity digest without disclosing credentials.
   Count the run as successful only after the complete encrypted object is
   available and verified in R2. A failed or partial upload must leave no
   artifact eligible for restore.

## First restore rehearsal

Use a pinned OpenBao 2.7.3 instance on a trusted Linux workstation with
isolated networking and verified memory-backed storage. Fetch the object with
the recovery credential and verify its integrity. Recover the matching wrapped
unseal share and any backup decryption material independently of the running
Trust instance. Develop and verify the exact initialization, restore, reseal,
and unseal sequence against disposable data before using it on the R2 artifact.
The rehearsal targets a disposable restore instance only.

Before the backup, create a non-secret verification fixture in Trust. After
restore, verify administrative access and read back that fixture. Record the
snapshot identity, elapsed time, memory usage and outcome. As transit is added,
include a fixture that proves decryption of a payload sealed before the backup.
Keep the replacement-Pi drill as a separate acceptance target.

## After the rehearsal

Automate the proven job. Set the schedule and R2 lifecycle retention using the
acceptable recovery point and observed snapshot sizes. A daily backup with
30 days of retention is the starting proposal. Record how failures surface and
how the operator verifies the newest successful backup. Revisit retirement of
the initial root token once the recovery path has been rehearsed.

## References

- [OpenBao Raft snapshot API](https://openbao.org/docs/api/system/storage/raft/)
- [Cloudflare R2 API tokens](https://developers.cloudflare.com/r2/api/tokens/)
- [Cloudflare R2 lifecycle rules](https://developers.cloudflare.com/r2/buckets/object-lifecycles/)
