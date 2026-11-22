#!/bin/sh
set -eu
umask 077
cd /work
export TMPDIR=/work
export PATH="/tools:$PATH"
. /scripts/freshness.sh
read_credential() { cat "/credentials/$1"; }
AWS_ACCESS_KEY_ID=$(read_credential access-key-id)
AWS_SECRET_ACCESS_KEY=$(read_credential secret-access-key)
export AWS_ACCESS_KEY_ID AWS_SECRET_ACCESS_KEY
export RESTIC_PASSWORD_FILE=/credentials/password
repo() { restic --no-cache --no-lock -o s3.region=auto "$@"; }
service_account=/var/run/secrets/kubernetes.io/serviceaccount
api_host=${KUBERNETES_SERVICE_HOST:?Missing Kubernetes API host}
case "$api_host" in
    *:*) api_host="[$api_host]" ;;
esac
cat > /work/kubeconfig <<EOF
apiVersion: v1
kind: Config
clusters:
- name: trust
  cluster:
    server: https://${api_host}:${KUBERNETES_SERVICE_PORT_HTTPS:-443}
    certificate-authority: $service_account/ca.crt
users:
- name: restore
  user:
    tokenFile: $service_account/token
contexts:
- name: restore
  context:
    cluster: trust
    user: restore
current-context: restore
EOF
kube() {
    kubectl --kubeconfig=/work/kubeconfig --cache-dir=/work/kube-cache \
        -n openbao-restore --request-timeout=30s "$@"
}
pod=pod/openbao-restore-0
sts=statefulset/openbao-restore
claim=pvc/data-openbao-restore-0
remote() { kube exec "$pod" -c openbao -- "$@"; }

latest=$(repo snapshots --json --host trust-openbao --tag trust-openbao-complete \
    --latest 1)
id=$(printf '%s' "$latest" | jq -er 'select(length == 1) | .[0].id |
    select(test("^[0-9a-f]{64}$"))') || { echo "No completed OpenBao backup found" >&2; exit 1; }
printf 'Selected restic backup %s\n' "$id"
repo restore "$id" --target /work/snapshot --verify
meta=/work/snapshot/metadata.json
file=/work/snapshot/raft.snap
created=$(jq -er '.created_at | numbers | select(. == floor)' "$meta")
printf 'Raft snapshot created_at=%s (UTC epoch seconds)\n' "$created"
check_freshness "$created" "$(date -u +%s)"
source_version=$(jq -er '.openbao_version | strings' "$meta")
[ "$source_version" = "$RESTORE_VERSION" ] || { echo "Restore release version differs from backup" >&2; exit 1; }
expected=$(jq -er '.sha256 | select(test("^[0-9a-f]{64}$"))' "$meta")
actual=$(sha256sum "$file")
[ "${actual%% *}" = "$expected" ] || { echo "Raft snapshot digest mismatch" >&2; exit 1; }

target=$(kube get "$sts" -o json)
printf '%s' "$target" | jq -e --arg image "$RESTORE_IMAGE" '
    .metadata.namespace == "openbao-restore" and
    (.spec.template.spec.containers | any(.name == "openbao" and .image == $image)) and
    (.spec.volumeClaimTemplates | any(.metadata.name == "data" and
        .spec.storageClassName == "trust-zfs-rehearsal")) and
    (.spec.replicas == 1 or .spec.replicas == 0)' >/dev/null
existing=$(kube get "$claim" --ignore-not-found -o json)
if [ -n "$existing" ]; then
    printf '%s' "$existing" | jq -e '.spec.storageClassName == "trust-zfs-rehearsal"' >/dev/null
fi
check_freshness "$created" "$(date -u +%s)"
printf 'Resetting dedicated restore claim for id=%s age=%ss\n' "$id" "$age"
kube scale "$sts" --replicas=0
wait_deleted() {
    deadline=$(( $(date -u +%s) + 120 ))
    while :; do
        resource=$(kube get "$1" --ignore-not-found -o name)
        [ -n "$resource" ] || return 0
        [ "$(date -u +%s)" -lt "$deadline" ] || { echo "Timed out deleting $1" >&2; exit 1; }
        sleep 2
    done
}
wait_deleted "$pod"
kube delete "$claim" --ignore-not-found --wait=false
wait_deleted "$claim"
kube scale "$sts" --replicas=1
deadline=$(( $(date -u +%s) + 180 ))
while :; do
    code=0
    state=$(remote bao status -format=json 2>/dev/null) || code=$?
    if [ "$code" -eq 2 ] && printf '%s' "$state" | jq -e \
        '.initialized == false and .sealed == true' >/dev/null 2>&1; then
        break
    fi
    [ "$(date -u +%s)" -lt "$deadline" ] || { echo "Empty restore target did not start" >&2; exit 1; }
    sleep 3
done

# These credentials belong only to the empty rehearsal instance. The source
# Shamir share and root token are needed only for the optional operator check.
init=$(remote bao operator init -format=json -key-shares=1 -key-threshold=1)
share=$(printf '%s' "$init" | jq -ec '{key:(.unseal_keys_b64[0] | strings | select(length > 0))}')
token=$(printf '%s' "$init" | jq -er '.root_token | strings | select(length > 0)')
unset init
printf '%s' "$share" | kube exec -i "$pod" -c openbao -- \
    bao write -format=json sys/unseal - >/dev/null
unset share

# Pass the short-lived rehearsal root token and snapshot through stdin.
# Keep the remote temporary file on the restore container's tmpfs.
{
    printf '%s\n' "$token"
    cat "$file"
} | kube --request-timeout=5m exec -i "$pod" -c openbao -- sh -ec '
    umask 077
    IFS= read -r BAO_TOKEN
    export BAO_TOKEN
    file=$(mktemp /tmp/restore.XXXXXX)
    trap "rm -f -- \"$file\"" EXIT
    cat > "$file"
    bao operator raft snapshot restore -force "$file"
' >/dev/null
unset token

deadline=$(( $(date -u +%s) + 90 ))
while :; do
    code=0
    state=$(remote bao status -format=json 2>/dev/null) || code=$?
    if [ "$code" -eq 2 ] && printf '%s' "$state" | jq -e \
        '.initialized == true and .sealed == true' >/dev/null 2>&1; then
        break
    fi
    [ "$(date -u +%s)" -lt "$deadline" ] || { echo "Restored OpenBao did not become sealed" >&2; exit 1; }
    sleep 2
done
check_freshness "$created" "$(date -u +%s)"
printf 'RESTORE PASSED id=%s created_at=%s age=%ss sha256=%s sealed=true\n' \
    "$id" "$created" "$age" "$expected"
