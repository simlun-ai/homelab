#!/bin/sh
set -eu
umask 077
cd /work
export TMPDIR=/work
read_credential() { cat "/credentials/$1"; }
AWS_ACCESS_KEY_ID=$(read_credential access-key-id)
AWS_SECRET_ACCESS_KEY=$(read_credential secret-access-key)
export AWS_ACCESS_KEY_ID AWS_SECRET_ACCESS_KEY
export RESTIC_PASSWORD_FILE=/credentials/password

if [ "${1:-}" = init ]; then
    exec restic --no-cache -o s3.region=auto init
fi

export BAO_ADDR=https://openbao.openbao.svc:8200
export BAO_TLS_SERVER_NAME=bao.k8s-aux.simlun.se
export BAO_DISABLE_REDIRECTS=1
version=$(/tools/bao status -format=json | /tools/jq -er '.version')
[ "$version" = "$SOURCE_VERSION" ] || { echo "Unexpected source OpenBao version" >&2; exit 1; }
BAO_TOKEN=$(/tools/bao write -field=token auth/trust-backup/login \
    role=snapshot jwt=@/identity/token)
export BAO_TOKEN
created_at=$(date -u +%s)
/tools/bao operator raft snapshot save raft.snap
unset BAO_TOKEN
digest=$(sha256sum raft.snap)
digest=${digest%% *}
/tools/jq -n --arg version "$version" --arg sha256 "$digest" \
    --argjson created_at "$created_at" \
    '{openbao_version:$version,sha256:$sha256,created_at:$created_at}' > metadata.json

run_tag="job-$POD_UID"
# A successful restic exit is required before publishing the completion tag.
# restic may otherwise leave a partial snapshot after an input error.
restic --no-cache -o s3.region=auto backup --json --host trust-openbao \
    --tag "$run_tag" raft.snap metadata.json > backup.json
snapshot=$(/tools/jq -er 'select(.message_type == "summary") | .snapshot_id |
    select(test("^[0-9a-f]{64}$"))' backup.json)
restic --no-cache -o s3.region=auto tag --add trust-openbao-complete "$snapshot"
complete=$(restic --no-cache -o s3.region=auto snapshots --json \
    --tag "trust-openbao-complete,$run_tag")
id=$(printf '%s' "$complete" | /tools/jq -er 'select(length == 1) | .[0].id')
printf 'BACKUP COMPLETE id=%s created_at=%s sha256=%s\n' "$id" "$created_at" "$digest"

log_bucket_size() {
    phase=$1
    address=${RESTIC_REPOSITORY#s3:https://}
    endpoint=${address%%/*}
    path=${address#*/}
    bucket=${path%%/*}
    if [ -x /tools/s5cmd ] &&
       usage=$(AWS_REGION=auto timeout 15 /tools/s5cmd --json --retry-count 1 \
           --endpoint-url "https://$endpoint" du "s3://$bucket/*" 2>/work/bucket-size.stderr) &&
       [ ! -s /work/bucket-size.stderr ] &&
       bytes=$(printf '%s\n' "$usage" | /tools/jq -es '
           select(length == 1) | .[0].size | numbers | select(. >= 0 and . == floor)'); then
        printf 'R2 BUCKET SIZE phase=%s bytes=%s id=%s\n' "$phase" "$bytes" "$id"
    else
        printf 'R2 BUCKET SIZE UNAVAILABLE phase=%s id=%s\n' "$phase" "$id" >&2
    fi
}

log_bucket_size before_prune
printf 'RESTIC RETENTION STARTED id=%s\n' "$id"
if ! restic --no-cache -o s3.region=auto forget --prune \
    --host trust-openbao --tag trust-openbao-complete \
    --keep-within-daily 7d --keep-within-weekly 30d \
    --keep-within-monthly 1y --keep-within-yearly 5y; then
    printf 'RESTIC RETENTION FAILED id=%s\n' "$id" >&2
    exit 1
fi
printf 'RESTIC RETENTION PASSED id=%s\n' "$id"
log_bucket_size after_prune

printf 'RESTIC CHECK STARTED id=%s\n' "$id"
if ! restic --no-cache -o s3.region=auto check; then
    printf 'RESTIC CHECK FAILED id=%s\n' "$id" >&2
    exit 1
fi
printf 'RESTIC CHECK PASSED id=%s\n' "$id"
