#!/bin/sh
set -eu
IFS= read -r BAO_TOKEN
export BAO_TOKEN
export BAO_ADDR=https://127.0.0.1:8200
export BAO_TLS_SERVER_NAME=bao.k8s-aux.simlun.se
export BAO_DISABLE_REDIRECTS=1

if ! bao secrets list -format=json | grep -q '"workload-kv/":'; then
    bao secrets enable -path=workload-kv -version=2 kv
fi
# Require compare-and-set (CAS) on KV writes to prevent accidental overwrites.
# Seeding uses cas=0 to create a new entry. Updating an existing entry requires its current version.
bao write workload-kv/config cas_required=true

bao policy write trust-workload-check - <<'EOF'
path "workload-kv/metadata/trust/*" { capabilities = ["read"] }
EOF
bao policy write trust-workload-seed - <<'EOF'
path "workload-kv/metadata/trust/*" { capabilities = ["read"] }
path "workload-kv/data/trust/*" { capabilities = ["create"] }
EOF
bao policy write trust-eso-smoke - <<'EOF'
path "sys/mounts/workload-kv" { capabilities = ["read"] }
path "workload-kv/data/trust/eso-smoke/allowed" { capabilities = ["read"] }
EOF
if ! bao auth list -format=json | grep -q '"trust-eso/":'; then
    bao auth enable -path=trust-eso kubernetes
fi
bao write auth/trust-eso/config kubernetes_host=https://kubernetes.default.svc:443
bao write auth/trust-eso/role/smoke \
    bound_service_account_names=eso-smoke bound_service_account_namespaces=eso-smoke \
    audience=trust-eso-smoke token_policies=trust-eso-smoke \
    token_type=batch token_no_default_policy=true token_ttl=5m token_max_ttl=5m
