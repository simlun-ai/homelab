# Trust workload secrets

The Trust workload root defines External Secrets Operator (ESO). It uses
OpenBao's KV v2 mount `workload-kv` to supply Kubernetes Secrets to
workloads that start after OpenBao is unsealed. Bootstrap and OpenBao
recovery credentials remain independently recoverable. The images needed
to start OpenBao and ESO must be available independently of Zot.

## Deploy and bootstrap

With Trust running and OpenBao unsealed, run from the homelab checkout:

```sh
make -C clusters/trust tofu-workload-plan
make -C clusters/trust tofu-workload-apply
make -C clusters/trust openbao-secrets-bootstrap
```

Expect the `external-secrets` namespace and Helm release in the plan.
Bootstrap uses the existing wrapped OpenBao root credential to create or
reconcile the mount, policies, and ESO roles. It leaves existing KV
entries intact. The inventory commands use that credential to mint a
five-minute token scoped to metadata reads and, for seeding, creation.

## Check and seed

```sh
make -C clusters/trust openbao-secrets-check
make -C clusters/trust openbao-secrets-seed
make -C clusters/trust openbao-secrets-check
```

The first check will report missing entries on a fresh mount. Seed
creates missing `generate` entries with KV v2 check-and-set. Reruns keep
existing entries. The inventory is in
[`clusters/trust/openbao/inventory.json`](../../clusters/trust/openbao/inventory.json).
Add an entry with a path, owner, consumers, strategy, and recovery
instruction. `operator-input` and `restore` entries report required
action when missing. Deleted or destroyed KV versions report `recover`.
The commands report statuses and exit nonzero when any entry needs action.

After a rebuild, restore OpenBao from its Raft backup before running the
check. Use the recovery instructions for missing entries. Transit keys
are outside this KV inventory and must retain the key versions used by
existing Talos disks.

## Verify the disposable ESO setup

```sh
make -C clusters/trust trust-kubectl \
  KUBECTL_ARGS='apply -f openbao/eso-smoke.yaml'
make -C clusters/trust trust-kubectl \
  KUBECTL_ARGS='-n eso-smoke wait --for=condition=Ready externalsecret/allowed --timeout=2m'
make -C clusters/trust trust-kubectl \
  KUBECTL_ARGS='-n eso-smoke describe externalsecret/denied'
```

Confirm the denied request reports an OpenBao permission error. Both
test values should be present according to the inventory check. Verify
refresh by deleting the disposable target, waiting for recreation, and
checking that only the allowed Secret exists:

```sh
make -C clusters/trust trust-kubectl KUBECTL_ARGS='-n eso-smoke delete secret allowed'
make -C clusters/trust trust-kubectl \
  KUBECTL_ARGS='-n eso-smoke wait --for=create secret/allowed --timeout=2m'
make -C clusters/trust trust-kubectl KUBECTL_ARGS='-n eso-smoke get secrets'
make -C clusters/trust trust-kubectl KUBECTL_ARGS='delete namespace eso-smoke'
```

Deleting the smoke namespace removes the Kubernetes fixtures. The two
disposable OpenBao values remain available for a repeat verification.
Record the live verification in the [Trust roadmap](02-trust.md), then
[publish the encrypted workload state](trust-openbao.md#publish-encrypted-workload-state).
