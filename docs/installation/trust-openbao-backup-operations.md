# Operate scheduled Trust OpenBao backups

The CronJob on `trust-cp1` runs daily at 02:30 UTC. It takes an OpenBao Raft
snapshot, backs it up directly to a private R2 bucket with restic, and
retrieves that exact restic snapshot using a read-only R2 credential. A fresh
OpenBao instance imports the verified snapshot and reaches the sealed state.
The job discards the rehearsal data when it terminates. The sole DR test is
this restore path on Trust, with a separate YubiKey check for fixture readback.

The restore server uses a loopback listener, has no Service or Kubernetes
identity, and has no R2 credentials. It runs under an outbound socket filter
so restored integrations cannot call out during the rehearsal. The Job uses
memory-backed staging with a 64 MiB Raft snapshot limit and a 512 MiB container
memory limit. Review actual headroom and adjust these limits together if the
snapshot or restore database grows. All scheduled phases must fit the
20-minute Job deadline.

## Provision the R2 bucket and wrapped records

Create a dedicated private R2 bucket. Create a bucket-scoped **Object Read &
Write** S3 credential for backup and a separate **Object Read only** S3
credential for readback and recovery. Record the account endpoint, bucket,
and restic repository path in the recovery guide.

From the homelab checkout root on the Trust operator workstation, with the
YubiKey attached, sync the wrapped-record checkout and enroll the three
records. The helper generates the repository password and prompts without
echoing the two R2 key pairs.

```sh
git switch feat/trust-bootstrap &&
  git pull --ff-only --no-recurse-submodules &&
  git -C secrets/wrapped switch main &&
  git -C secrets/wrapped pull --ff-only &&
  make -C clusters/trust openbao-backup-enroll
```

Review the private checkout before committing. The three new files are
`trust-openbao-restic-password-r1.json`, `trust-openbao-r2-writer-r1.json`,
and `trust-openbao-r2-reader-r1.json`.

```sh
git -C secrets/wrapped status --short --branch
```

```sh
git -C secrets/wrapped add --   trust-openbao-restic-password-r1.json trust-openbao-r2-writer-r1.json trust-openbao-r2-reader-r1.json &&
git -C secrets/wrapped commit --only -m 'Record wrapped OpenBao backup credentials' --   trust-openbao-restic-password-r1.json trust-openbao-r2-writer-r1.json trust-openbao-r2-reader-r1.json &&
git -C secrets/wrapped push origin main &&
git pull --ff-only --no-recurse-submodules &&
git add -- secrets/wrapped &&
git commit --only -m 'Pin wrapped OpenBao backup credentials' -- secrets/wrapped &&
git push origin feat/trust-bootstrap
```

## Configure and enable

Replace the account ID and bucket in the example. Use a dedicated repository
path in the bucket.

```sh
make -C clusters/trust openbao-backup-configure   R2_REPOSITORY='s3:https://ACCOUNT_ID.r2.cloudflarestorage.com/BUCKET/trust-openbao'
```

The helper uses the wrapped bootstrap root token over verified HTTPS to
configure a dedicated OpenBao Kubernetes auth mount, a snapshot-only policy,
and a non-secret KV v2 fixture. The OpenBao server's existing service account
receives TokenReview permission. Only the backup container gets the projected
backup service account token. OpenBao issues a ten-minute token for snapshot
reads. The helper sends the R2 credentials and restic password to their
separate Kubernetes Secrets over the Trust admin connection from memory.
The job's resources are operator-managed through this helper.

Initialize the restic repository once. For an existing repository, proceed
to enable, which checks repository access before starting the schedule.

```sh
make -C clusters/trust openbao-backup-init-repo
```

```sh
make -C clusters/trust openbao-backup-enable
```

After the schedule runs, check the Job and record the full snapshot ID from
the completed restore. A successful run prints the same ID at all three
checkpoints.

```sh
make -C clusters/trust openbao-backup-status
```

- `BACKUP COMPLETE` means restic returned a successful snapshot ID.
- `R2 READBACK VERIFIED` means the read-only credential retrieved the entire
  snapshot and the Raft file matched its recorded digest.
- `RESTORE APPLIED SEALED` means the disposable OpenBao server accepted the
  snapshot and reached the sealed state.

Suspend future jobs for maintenance with the following command.
Check status and let any active job finish before repository maintenance.

```sh
make -C clusters/trust openbao-backup-disable
```

## Verify the restored fixture with a YubiKey

Copy the full ID from a successful scheduled run. Run this outside the
scheduled window to avoid overlapping the rehearsal with another restore
on the Pi.

```sh
make -C clusters/trust openbao-backup-verify RESTORE_SNAPSHOT_ID=FULL_RESTIC_SNAPSHOT_ID
```

The helper retrieves that snapshot again using the read-only credential and
applies it to a fresh temporary server. Once it reaches the sealed
checkpoint, touch the YubiKey to recover the source unseal share and wrapped
root token. The helper streams both over authenticated Kubernetes exec into
the rehearsal container, unseals the restored instance, and reads the fixture.
The share and root token remain out of the CronJob and its Kubernetes Secrets.
Expect `PASS: restored OpenBao fixture matched`. The verification Job has a
ten-minute verification window and terminates after the check.

Confirm production still serves HTTPS.

```sh
curl --fail --silent --show-error --noproxy '*' --max-time 10   https://bao.k8s-aux.simlun.se/v1/sys/health
```

Record the snapshot ID, backup/rehearsal durations, memory headroom, result,
and production health. For failures, inspect the Job and pod events and the
phase reported by `openbao-backup-status`. Keep the existing verified recovery
point until a new run completes. Follow the separate offline copy plan for
deletion protection. Repository pruning and offline-copy automation remain
operator work.
