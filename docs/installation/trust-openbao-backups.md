# Trust OpenBao snapshot and restore milestone

Status on 2026-11-22. The [operator runbook](trust-openbao-backup-operations.md)
covers separate backup and restore schedules. A manual backup and restore
passed. Scheduled verification is tracked in the [Trust installation roadmap](02-trust.md#current-position).

The backup CronJob in `openbao` takes an online native Raft snapshot and
uploads it directly to R2 with restic. The separate restore CronJob runs at
05:00 Europe/Stockholm. It checks the digest and original creation time,
rejects snapshots at least 24 hours old, and imports the snapshot into the
dedicated `openbao-restore` Helm release. The rehearsal release is separate
from production and can also be used for upgrade testing.

## Restic repository maintenance

The backup Job configuration runs `restic check` after publishing a completed snapshot.
This verifies repository structure. The separate restore Job verifies
the contents of the selected snapshot.

- [ ] Choose retention for completed snapshots. The starting proposal is
  to keep 30 days with `--keep-within 30d`.
- [ ] Run `restic forget --prune` before the repository check after a successful
  backup. Coordinate pruning with the read-only restore Job, which
  does not take a repository lock, and with the offline copy procedure.

## Offline copy of R2

Use direct R2 access with a bucket-scoped job credential. The operator will
regularly copy all R2 data to a separate drive kept offline between copy runs.
The offline copy protects against accidental deletion and malware. Copy the
complete encrypted restic repository, including its metadata, and retain a
previous usable copy when refreshing it so deletions in R2 do not erase the
offline recovery point. The copy schedule and tooling remain to be decided.

## Disaster recovery rehearsal on Trust

The automatic check verifies download, integrity, snapshot freshness, and
successful import into the rehearsal OpenBao release. Its success receipt
includes the restic ID, Raft digest, original snapshot timestamp, and sealed
status. Production remains online throughout the rehearsal. The operator can
pause the restore schedule, unseal the instance using the wrapped share, and
inspect the restored data with the OpenBao CLI. This is the sole OpenBao
disaster recovery rehearsal.

The restore release uses a separate Raft claim, a loopback TLS listener,
and a namespace-local CA. Backup and restore credentials are separate and
the restore server receives neither. Restic retention and the offline copy
schedule remain operator decisions.

## References

- [OpenBao Raft snapshot API](https://openbao.org/docs/api/system/storage/raft/)
- [Cloudflare R2 API tokens](https://developers.cloudflare.com/r2/api/tokens/)
- [Cloudflare R2 lifecycle rules](https://developers.cloudflare.com/r2/buckets/object-lifecycles/)
