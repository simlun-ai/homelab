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
   bucket and restic repository path in the emergency recovery guide. Create
   separate bucket-scoped
   credentials for the in-cluster uploader and the read-only restore operator.
   Keep the wrapped recovery credential independently available before Trust
   starts.
2. Use the wrapped initial root token in a manual, memory-only workstation
   session to configure a dedicated OpenBao backup identity. Grant it access to
   the Raft snapshot endpoint. Verify that it can take a snapshot and that it
   cannot restore snapshots or administer secrets. Use a short-lived job token.
   Decide how the job obtains that token and how the R2 credential reaches the
   pod using the existing wrapped-record workflow.
3. Run restic directly against the private R2 bucket using its S3 backend.
   Stage the native Raft snapshot in bounded memory-backed storage in the
   Trust job and upload it as an encrypted restic backup. Set job deadlines,
   cleanup, and failure reporting. Keep the restic repository password
   independently recoverable through the wrapped-record workflow.
4. Run a single backup job in Trust. Record the Raft snapshot identity, OpenBao
   version, digest, and restic snapshot ID. Count the backup as successful
   after restic publishes the snapshot and its contents can be verified.

## Offline copy of R2

Use direct R2 access with a bucket-scoped job credential. The operator will
regularly copy all R2 data to a separate drive kept offline between copy runs.
The offline copy protects against accidental deletion and malware. Copy the
complete encrypted restic repository, including its metadata, and retain a
previous usable copy when refreshing it so deletions in R2 do not erase the
offline recovery point. The copy schedule and tooling remain to be decided.

## Disaster recovery rehearsal on Trust

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
nor outbound access. Restore the Raft snapshot from the encrypted restic repository into
bounded, memory-backed storage on Trust.

Recover the read-only R2 credential, restic repository password, and
matching wrapped unseal share through the workstation's YubiKey workflow.
Use the recovery credential and password to retrieve and verify the snapshot.
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

This is the sole OpenBao disaster recovery rehearsal. Its scope is R2
retrieval and application restore on the existing Trust cluster.

## After the rehearsal

Automate the proven job. Use restic retention for the live repository and
choose the schedule from the acceptable recovery point and measured backup
sizes. Daily backups with 30 days of restic retention are the starting
proposal. Record how failures surface and
how the operator verifies the newest successful backup. Revisit retirement of
the initial root token once the recovery path has been rehearsed.

## References

- [OpenBao Raft snapshot API](https://openbao.org/docs/api/system/storage/raft/)
- [Cloudflare R2 API tokens](https://developers.cloudflare.com/r2/api/tokens/)
- [Cloudflare R2 lifecycle rules](https://developers.cloudflare.com/r2/buckets/object-lifecycles/)
