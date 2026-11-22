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

After publishing a completed snapshot, the backup Job applies retention with
`restic forget --prune`, then verifies repository structure with `restic check`.
Retention applies to snapshots from host `trust-openbao` tagged
`trust-openbao-complete`. Restic applies all four rules and keeps snapshots that
match any rule. Each window is measured back from the latest completed snapshot.

| Snapshot frequency | Retention window |
| --- | --- |
| Daily | 7 days |
| Weekly | 30 days |
| Monthly | 1 year |
| Yearly | 5 years |

The windows overlap and can span partial calendar periods. For sizing, allow
up to 34 completed snapshots per backup set. That counts up to 8 daily,
6 weekly, 13 monthly and 6 yearly periods plus one oldest-snapshot fallback.
Some snapshots satisfy multiple rules, so the usual count is lower.

The first rehearsal restored 27.662 KiB of snapshot and metadata. At that
size, 34 independent copies total about 0.92 MiB before restic metadata,
compression and deduplication. Budget **about 2 MiB of steady-state R2
storage after five years** at the observed snapshot size, with headroom for
repository metadata and retained pack data. This estimate excludes temporary
prune space, incomplete snapshots, offline copies and future OpenBao data
growth. For a larger snapshot, multiply its measured size by 34 before
allowing for repository overhead.

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
the restore server receives neither.

## References

- [OpenBao Raft snapshot API](https://openbao.org/docs/api/system/storage/raft/)
- [Cloudflare R2 API tokens](https://developers.cloudflare.com/r2/api/tokens/)
- [Cloudflare R2 lifecycle rules](https://developers.cloudflare.com/r2/buckets/object-lifecycles/)
- [Restic 0.18.1 snapshot retention and pruning](https://restic.readthedocs.io/en/v0.18.1/060_forget.html)
