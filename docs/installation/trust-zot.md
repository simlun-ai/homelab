# Deploy Zot on Trust

Trust's workload root defines one Zot replica with a 20 GiB
`trust-zfs-retain` claim on the encrypted `trust-data` ZFS mirror.
Zot terminates HTTPS with a cert-manager certificate. LAN clients can
pull anonymously. The `publisher` account can create and update images
under `homelab/**`.

## Deploy the workload

Confirm `10.10.0.201` is free, then point the UniFi internal DNS record
for `registry.k8s-aux.simlun.se` at it. Allow LAN access to TCP 443 and
keep the endpoint off the WAN.

From the homelab checkout root on the operator workstation:

```sh
make -C clusters/trust tofu-workload-plan
```

Expect a new namespace and Helm release for Zot. Apply the plan:

```sh
make -C clusters/trust tofu-workload-apply
```

The Zot pod waits for its certificate and the publisher verifier supplied by ESO.

## Enroll the publisher

Run `make -C clusters/trust tools` on the workstation to provision
`htpasswd`. On Debian and Ubuntu it comes from `apache2-utils`, and on
Arch it comes from `apache`. A missing package may prompt for sudo.
With OpenBao unsealed, reconcile its Zot role and seed the workload
inventory. OpenBao holds the publisher password and a separate bcrypt
verifier entry. ESO can read only the verifier and syncs it to the
`zot-publisher` Kubernetes Secret.

```sh
make -C clusters/trust openbao-secrets-bootstrap &&
make -C clusters/trust openbao-secrets-seed &&
make -C clusters/trust trust-kubectl \
  KUBECTL_ARGS='-n zot wait --for=condition=Ready externalsecret/zot-publisher --timeout=5m' &&
make -C clusters/trust trust-kubectl \
  KUBECTL_ARGS='-n zot wait --for=condition=Ready certificate/zot --timeout=5m' &&
make -C clusters/trust trust-kubectl \
  KUBECTL_ARGS='-n zot rollout status statefulset/zot --timeout=5m'
make -C clusters/trust trust-kubectl KUBECTL_ARGS='-n zot get pvc,pv,service'
```

Expect a bound `trust-zfs-retain` claim and `zot-https` at `10.10.0.201`.
An anonymous upload request should return HTTP 401 or 403:

```sh
curl -sS -o /dev/null -w '%{http_code}\n' -X POST \
  https://registry.k8s-aux.simlun.se/v2/homelab/zot-verification/blobs/uploads/
```

## Publish the first image

Use the operator workstation's Docker Buildx setup. The following uses a
temporary Docker configuration in protected RAM and removes it when the
command exits. Run from the homelab checkout root:

```bash
bash <<'BASH'
set -euo pipefail
umask 077
registry=registry.k8s-aux.simlun.se
export DOCKER_CONFIG
DOCKER_CONFIG=$(mktemp -d /dev/shm/trust-zot-docker.XXXXXXXX)
trap 'rm -rf -- "$DOCKER_CONFIG"' EXIT
make -s --no-print-directory -C clusters/trust openbao-secrets-zot-publisher |
  python3 -c 'import base64,json,sys; p=sys.stdin.buffer.read().rstrip(b"\n"); assert p, "Publisher password unavailable"; print(json.dumps({"auths": {sys.argv[1]: {"auth": base64.b64encode(b"publisher:" + p).decode("ascii")}}}))' \
    "$registry" >"$DOCKER_CONFIG/config.json"
docker buildx build --platform linux/arm64 --push \
  --file clusters/trust/containers/talos-kms/Dockerfile \
  --tag "$registry/homelab/talos-kms:$(git rev-parse --short HEAD)" \
  --metadata-file "$DOCKER_CONFIG/image.json" .
jq -er '."containerimage.digest"' "$DOCKER_CONFIG/image.json"
BASH
```

Use a credential-free OCI client to pull
`registry.k8s-aux.simlun.se/homelab/talos-kms@sha256:...` with the
reported digest. Recreate the Zot pod with a StatefulSet rollout restart
and repeat the pull by digest once it is ready to verify persistence.
After a clean workload plan, follow the [encrypted workload state
publication procedure](trust-openbao.md#publish-encrypted-workload-state).
