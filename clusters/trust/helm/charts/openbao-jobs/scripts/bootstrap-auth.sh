#!/bin/sh
set -eu
IFS= read -r BAO_TOKEN
export BAO_TOKEN
export BAO_TLS_SERVER_NAME=bao.k8s-aux.simlun.se
export BAO_DISABLE_REDIRECTS=1
printf '%s\n' 'path "sys/storage/raft/snapshot" { capabilities = ["read", "sudo"] }' |
    bao policy write trust-raft-snapshot -
if ! bao auth list -format=json | grep -q '"trust-backup/":'; then
    bao auth enable -path=trust-backup kubernetes
fi
bao write auth/trust-backup/config kubernetes_host=https://kubernetes.default.svc:443
bao write auth/trust-backup/role/snapshot \
    bound_service_account_names=openbao-backup \
    bound_service_account_namespaces=openbao \
    audience=trust-openbao-backup token_policies=trust-raft-snapshot \
    token_no_default_policy=true token_ttl=10m token_max_ttl=10m
