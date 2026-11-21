# Trust OpenBao snapshot and restore milestone

Status on 2026-11-22. The [operator runbook](trust-openbao-backup-operations.md)
covers the scheduled backup, automatic sealed restore and manual YubiKey
fixture check. Live R2 and Kubernetes verification are pending.

A daily CronJob exports the native Raft snapshot over TLS, backs it up
directly to R2 with restic, retrieves the exact snapshot with a separate
read-only credential, and loads it into a disposable second OpenBao instance
on Trust. Routine jobs finish at the sealed checkpoint. To validate restored
contents, the operator replays a selected snapshot and uses the YubiKey to
unseal the temporary server and read the fixture.

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

## After live verification

Review the measured backup sizes, memory use, and recovery time before
setting retention and pruning. Confirm failure reporting and the offline
copy cadence. Revisit retirement of the initial root token after the
YubiKey-backed fixture check is verified.

## References

- [OpenBao Raft snapshot API](https://openbao.org/docs/api/system/storage/raft/)
- [Cloudflare R2 API tokens](https://developers.cloudflare.com/r2/api/tokens/)
- [Cloudflare R2 lifecycle rules](https://developers.cloudflare.com/r2/buckets/object-lifecycles/)
