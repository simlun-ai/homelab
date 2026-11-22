#!/bin/sh
set -eu
name="talos-$1"
IFS= read -r BAO_TOKEN
export BAO_TOKEN
export BAO_ADDR=https://127.0.0.1:8200
export BAO_TLS_SERVER_NAME=bao.k8s-aux.simlun.se
export BAO_DISABLE_REDIRECTS=1

if ! bao secrets list -format=json | grep -q '"transit/":'; then
    bao secrets enable transit
fi
bao write "transit/keys/$name" type=aes256-gcm96
printf 'path "transit/encrypt/%s" { capabilities = ["update"] }\npath "transit/decrypt/%s" { capabilities = ["update"] }\n' "$name" "$name" |
    bao policy write "$name" -

if ! bao auth list -format=json | grep -q '"talos-kms/":'; then
    bao auth enable -path=talos-kms kubernetes
fi
bao write auth/talos-kms/config kubernetes_host=https://kubernetes.default.svc:443
bao write "auth/talos-kms/role/$name" \
    bound_service_account_names="$name" bound_service_account_namespaces=talos-kms \
    audience="$name" token_policies="$name" token_no_default_policy=true \
    token_type=batch token_ttl=5m token_max_ttl=5m
