# Trust OpenBao snapshot and restore milestone

Status on 2026-11-21. Planning. The first implementation is a manually
triggered Raft snapshot to Cloudflare R2, followed by a restore into a
disposable second OpenBao instance on the Trust Kubernetes cluster. HTTPS
and YubiKey-backed manual unseal are
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

## First restore rehearsal on Trust

Run a second single-replica OpenBao 2.7.3 instance on `trust-cp1` in a
dedicated rehearsal namespace. Use separate, disposable Raft storage, a
distinct Kubernetes identity, and explicit resource limits sized against the
snapshot and available Pi capacity. The production OpenBao instance stays
online on its existing claim throughout the drill.

Bind the rehearsal API to pod loopback. Use authenticated Kubernetes exec
for operator access. Keep the rehearsal instance outside production DNS,
MetalLB, and service discovery. Verify how to isolate restored workloads from
production integrations before starting the rehearsal. Use a separate
one-shot R2 downloader so the restore server needs neither the R2 credential
nor outbound access. Stage the downloaded object and decrypted snapshot in
bounded, memory-backed storage on Trust.

Retrieve the object with the independently held, read-only R2 credential
and verify its integrity. Recover the matching wrapped unseal share and any
backup decryption material through the workstation's YubiKey workflow.
Develop and verify the initialization, restore, reseal, and unseal sequence
using disposable data before restoring the R2 artifact. Use the rehearsal
namespace and loopback endpoint for every restore command.

Before the backup, create a non-secret fixture in production OpenBao. After
restore, verify administrative access to the rehearsal instance, read back
the fixture, and confirm the production endpoint still passes its health
check. Record the snapshot identity, elapsed time, resource usage, and
result. Remove the rehearsal workload, temporary credentials, and its
disposable storage. As transit is added, include a fixture that proves
decryption of a payload sealed before the backup.

This rehearsal covers R2 retrieval and OpenBao restore on existing Trust.
Recovery after losing Trust remains a separate milestone under
[required recovery targets](../backup-and-restore.md#required-recovery-targets).

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
