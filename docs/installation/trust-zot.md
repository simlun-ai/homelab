# Deploy Zot on Trust

Trust's workload root defines one Zot replica with a 20 GiB
`trust-zfs-retain` claim on the encrypted `trust-data` ZFS mirror.
Zot terminates HTTPS with a cert-manager certificate. LAN clients can
pull anonymously. The `publisher` account can create and update images
under `homelab/**`.

## Deploy the workload

Confirm `10.10.0.202` is free, then point the UniFi internal DNS record
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

The Zot pod waits for its certificate and publisher Secret.

## Enroll the publisher

Use the workstation HSM environment and initialized private records
checkout. Install Apache `htpasswd` on the workstation (`apache2-utils`
on Debian). Generate the record once, or recover the existing record.

```bash
bash <<'BASH'
set -euo pipefail
hsm="${HSM_VENV:-$HOME/.local/share/homelab/venvs/hsm}/bin"
record=secrets/wrapped/trust-zot-publisher-r1.json
test ! -e "$record"
openssl rand -base64 32 | tr -d '\n' |
  "$hsm/homelab-wrap" --stdin --root-key golden-1 \
    --key-id homelab/v1/trust/zot/publisher/r1 --output "$record"
BASH
```

Commit the ciphertext in the private records repository and pin its
revision in the homelab checkout. Install the bcrypt verifier and check
the deployment:

```sh
make -C clusters/trust zot-publisher-apply
make -C clusters/trust trust-kubectl \
  KUBECTL_ARGS='-n zot wait --for=condition=Ready certificate/zot --timeout=5m'
make -C clusters/trust trust-kubectl \
  KUBECTL_ARGS='-n zot rollout status statefulset/zot --timeout=5m'
make -C clusters/trust trust-kubectl KUBECTL_ARGS='-n zot get pvc,pv,service'
```

Expect a bound `trust-zfs-retain` claim and `zot-https` at `10.10.0.202`.
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
hsm="${HSM_VENV:-$HOME/.local/share/homelab/venvs/hsm}/bin"
registry=registry.k8s-aux.simlun.se
export DOCKER_CONFIG
DOCKER_CONFIG=$(mktemp -d /dev/shm/trust-zot-docker.XXXXXXXX)
trap 'rm -rf -- "$DOCKER_CONFIG"' EXIT
"$hsm/homelab-unwrap" --root-key golden-1 --stdout \
  --key-id homelab/v1/trust/zot/publisher/r1 \
  --input secrets/wrapped/trust-zot-publisher-r1.json |
  python3 -c 'import base64,json,sys; print(json.dumps({"auths": {sys.argv[1]: {"auth": base64.b64encode(b"publisher:" + sys.stdin.buffer.read()).decode("ascii")}}}))' \
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
