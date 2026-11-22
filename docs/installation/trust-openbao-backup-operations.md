# Operate Trust OpenBao backup and restore

The Trust workload root deploys a backup CronJob in `openbao` and a separate
`openbao-restore` Helm release and CronJob in the `openbao-restore` namespace.
The production OpenBao release keeps its existing values, Service, and Raft
claim. The new release uses the same chart and single-node Raft configuration
with a separate disposable `trust-zfs-rehearsal` claim, a loopback-only API,
and a namespace-local cert-manager CA. Both schedules start suspended.

The backup runs at 03:00 and the restore at 05:00 Europe/Stockholm. The backup
takes a native Raft snapshot and writes it to a private R2 repository with
restic. The restore reads the most recent completed restic snapshot using
the read-only credential and verifies the digest and the original snapshot
timestamp. A missing, future-dated, or at least 24-hour-old snapshot fails the
Job before the target is reset. After an accepted import, the restore Job
confirms that the target is initialized and sealed, then logs the snapshot ID,
source timestamp, age, and digest.

## Deploy the releases

Run from the homelab checkout root on the Trust operator workstation. Connect
the YubiKey and review the OpenTofu plan. Expect the rehearsal namespace and
two Helm releases to be added, with no changes to production OpenBao.

```sh
git switch feat/trust-bootstrap &&
  git pull --ff-only --no-recurse-submodules &&
  make -C clusters/trust tofu-workload-plan
```

```sh
make -C clusters/trust tofu-workload-apply
```

## Configure the backup repository

In Cloudflare R2, create a dedicated private bucket and two bucket-scoped
S3 credentials. Give the writer Object Read & Write and the reader Object
Read only. Record the endpoint, bucket, and repository path in the recovery
guide. Use three independently recoverable wrapped records for the two key
pairs and the restic repository password.

Create the password once. If the repository already exists, use its existing
password.

```bash
hsm="${HSM_VENV:-$HOME/.local/share/homelab/venvs/hsm}/bin"
openssl rand -base64 32 | tr -d '\n' |
  "$hsm/homelab-wrap" --stdin --root-key golden-1 \
    --key-id homelab/v1/trust/openbao-backup/restic-password/r1 \
    --output secrets/wrapped/trust-openbao-restic-password-r1.json
```

For the R2 credentials, run the following once with `role=writer`, then
again with `role=reader`. The keys are entered through the terminal and
passed to the wrapper over stdin.

```bash
(
  set -eu
  role=writer
  hsm="${HSM_VENV:-$HOME/.local/share/homelab/venvs/hsm}/bin"
  read -rsp "R2 $role access key ID: " access </dev/tty
  printf '\n'
  read -rsp "R2 $role secret access key: " secret </dev/tty
  printf '\n'
  [ -n "$access" ] && [ -n "$secret" ]
  printf '%s\n%s\n' "$access" "$secret" |
    python3 -c 'import json,sys; a,b=sys.stdin.read().splitlines(); print(json.dumps({"access-key-id":a,"secret-access-key":b}))' |
    "$hsm/homelab-wrap" --stdin --root-key golden-1 \
      --key-id "homelab/v1/trust/openbao-backup/r2-$role/r1" \
      --output "secrets/wrapped/trust-openbao-r2-$role-r1.json"
)
```

Review the private checkout, commit only the three new ciphertext records,
push them to its private `main`, and pin the submodule revision.

```sh
git -C secrets/wrapped status --short --branch
git -C secrets/wrapped add -- trust-openbao-restic-password-r1.json \
  trust-openbao-r2-writer-r1.json trust-openbao-r2-reader-r1.json &&
  git -C secrets/wrapped commit --only -m 'Record wrapped OpenBao backup credentials' -- \
    trust-openbao-restic-password-r1.json trust-openbao-r2-writer-r1.json trust-openbao-r2-reader-r1.json &&
  git -C secrets/wrapped push origin main &&
  git pull --ff-only --no-recurse-submodules &&
  git add -- secrets/wrapped &&
  git commit --only -m 'Pin OpenBao backup credentials' -- secrets/wrapped &&
  git push origin feat/trust-bootstrap
```

Replace the account and bucket in the URL, then configure the separate
Kubernetes Secrets and bootstrap the snapshot-only OpenBao identity. The
wrapped initial root token is used solely during this policy setup.

```sh
make -C clusters/trust openbao-jobs-credentials \
  R2_REPOSITORY='s3:https://ACCOUNT_ID.r2.cloudflarestorage.com/BUCKET/trust-openbao'
make -C clusters/trust openbao-backup-auth
```

For a new repository, initialize it once using the pinned backup tools.

```sh
make -C clusters/trust openbao-backup-init-repo
make -C clusters/trust trust-kubectl \
  KUBECTL_ARGS='-n openbao wait --for=condition=complete job/openbao-restic-init --timeout=180s'
```

## Enable and review the schedules

```sh
make -C clusters/trust trust-kubectl \
  KUBECTL_ARGS="-n openbao patch cronjob openbao-backup --type=merge -p '{\"spec\":{\"suspend\":false}}'"
make -C clusters/trust trust-kubectl \
  KUBECTL_ARGS="-n openbao-restore patch cronjob openbao-restore --type=merge -p '{\"spec\":{\"suspend\":false}}'"
```

```sh
make -C clusters/trust trust-kubectl KUBECTL_ARGS='-n openbao get cronjob,jobs'
make -C clusters/trust trust-kubectl KUBECTL_ARGS='-n openbao-restore get cronjob,jobs'
```

Use the actual Job name from the output. Inspect `BACKUP COMPLETE` and
`RESTORE PASSED` for the restic ID. Setup or image-download failures can be
inspected in the Job's pod events.

```sh
make -C clusters/trust trust-kubectl KUBECTL_ARGS='-n openbao logs job/BACKUP_JOB_NAME'
make -C clusters/trust trust-kubectl KUBECTL_ARGS='-n openbao-restore logs job/RESTORE_JOB_NAME'
```

After deployment verification, run the [encrypted workload state
publication procedure](trust-openbao.md#publish-encrypted-workload-state).

## Inspect a restored instance or test an upgrade

Pause the restore schedule and wait for any active restore Job to finish
before inspection or upgrade testing. The backup continues on its own
schedule. The next enabled restore discards the rehearsal claim.

```sh
make -C clusters/trust trust-kubectl \
  KUBECTL_ARGS="-n openbao-restore patch cronjob openbao-restore --type=merge -p '{\"spec\":{\"suspend\":true}}'"
make -C clusters/trust trust-kubectl KUBECTL_ARGS='-n openbao-restore get cronjob,jobs'
```

```sh
make -C clusters/trust openbao-restore-unseal
make -C clusters/trust openbao-restore-shell
```

In the shell, run `bao status`. The CLI uses the restore pod's loopback
listener and private CA. Operations that read data require authentication
from the restored snapshot. The shell opens without a token. Keep the
namespace isolated from production clients. The automatic job uses only
throwaway initialization credentials on the empty rehearsal target and
finishes with the imported data sealed.

Use `openbao-restore.json` to change the restore release's pinned chart and
application version independently. The restore CronJob checks that the
running target specification and backup source version match its expected
restore version before deleting the claim. Return to the source version
and re-enable the restore schedule when upgrade testing is finished.

The R2 repository is copied separately to the offline drive for deletion
protection. Coordinate pruning with restore readback, which uses read-only
R2 access and does not take a restic repository lock.
