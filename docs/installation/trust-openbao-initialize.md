# Initialize and unseal Trust OpenBao

Use the Trust operator workstation and a connected YubiKey. This procedure
starts with the [verified staged workload](trust-openbao.md) and the
[published workload state key](trust-openbao.md#enroll-the-workload-state-key).
The helper uses the existing in-memory Trust Kubernetes admin flow. It
runs the OpenBao CLI inside `openbao-0` against its loopback listener
with TLS verification for `bao.k8s-aux.simlun.se`.

## Before initialization

From the `homelab` checkout root, update the parent and inspect the private
wrapped-records checkout.

```sh
git switch feat/trust-bootstrap &&
  git pull --ff-only --no-recurse-submodules &&
  git -C secrets/wrapped status --short --branch
```

On a clean private `main` checkout, pull its current revision.

```sh
git -C secrets/wrapped pull --ff-only
```

Check the staged server.

```sh
make -C clusters/trust openbao-status
```

Expect `Initialized: False. Sealed: True.` for a fresh server. An initialized
server requires its existing credentials.

## Initialize once and publish the wrapped records

```sh
make -C clusters/trust openbao-initialize
```

Touch the YubiKey as prompted. The helper first recovers the already enrolled
workload state key to check YubiKey access. It then initializes Shamir with
one share and threshold one. It captures the initialization response in memory,
wraps the share and initial root token separately, and independently unwraps
both to verify the saved ciphertext. The initial root token is held for
bootstrap administration. Its eventual replacement and revocation belong
with the administration setup.

Keep the command running until both records verify. If wrapping or verification
fails, correct the problem and retry at the helper prompt, while the response
remains in memory. If the process exits after sending the initialization request,
run `make -C clusters/trust openbao-status` and inspect which wrapped records
were created. If the server is initialized and the share is unavailable,
preserve the claim and investigate the interrupted operation before proceeding.

After both records verify, check that only those two new records appear.

```sh
git -C secrets/wrapped status --short --branch
```

Commit the ciphertext and pin its private revision.

```sh
git -C secrets/wrapped add -- trust-openbao-unseal-share-1-r1.json trust-openbao-initial-root-token-r1.json &&
  git -C secrets/wrapped commit --only -m 'Record wrapped Trust OpenBao bootstrap credentials' \
    -- trust-openbao-unseal-share-1-r1.json trust-openbao-initial-root-token-r1.json &&
  git -C secrets/wrapped push origin main
```

```sh
git pull --ff-only --no-recurse-submodules &&
  git add -- secrets/wrapped &&
  git commit --only -m 'Pin Trust OpenBao bootstrap records' -- secrets/wrapped &&
  git push origin feat/trust-bootstrap
```

On 2026-11-21, the operator initialized the staged OpenBao server and
independently verified both wrapped records with the YubiKey. The records
were published to the private repository at `8932b41` and pinned on
`feat/trust-bootstrap` at [`a05d3b1`](https://github.com/simlun-ai/homelab/commit/a05d3b1).

## Unseal and verify

```sh
make -C clusters/trust openbao-unseal
```

Touch the YubiKey when prompted. The helper submits the share through stdin
and checks the resulting seal status. Expect
`PASS: OpenBao is initialized and unsealed.`

```sh
make -C clusters/trust openbao-status
```

Expect `Initialized: True. Sealed: False.` The [network rollout](trust-openbao-network.md) enables
the listener on the already-initialized Raft claim. After a restart, use the
same workstation unseal command.

On 2026-11-21, the operator unsealed the live server using the YubiKey-wrapped
share. The helper confirmed that OpenBao was initialized and unsealed.
A separate `make -C clusters/trust openbao-status` check returned
`Initialized: True. Sealed: False.`
