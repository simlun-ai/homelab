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
