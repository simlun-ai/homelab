# Trust OpenTofu bootstrap

Trust's first OpenTofu root installs the OpenEBS ZFS LocalPV 2.11.2 driver
and a disposable-test StorageClass on the existing `trust-data` pool.
The deployment uses OpenTofu 1.13.9, the locked Helm and Kubernetes
providers, and the upstream chart whose SHA-256 is pinned in
[`zfs-localpv.json`](../clusters/trust/tofu/zfs-localpv.json).
The cluster-specific [Helm values](../clusters/trust/helm/values/infrastructure/zfs-localpv.yaml)
configure the host ZFS binary, kubelet path, and placement on `trust-cp1`.
This is an infrastructure pilot. Workload deployment is still open.

## 1. Prepare tools and the state checkout

Run from the homelab checkout root on the designated operator workstation.
Initialize the public HSM tools and private wrapped-record submodules using
your normal Git credentials. Use the same Linux workstation, approved swap
configuration, HSM environment, and YubiKey as for Trust administration.
`RAM_ROOT` defaults to `/dev/shm` and must be on verified tmpfs.

```sh
git submodule update --init -- tools/homelab-hsm secrets/wrapped &&
  make -C support/hsm tools &&
  make -C clusters/trust tools tofu-tools
```

For the **first-ever** Trust state, initialize the sibling checkout if it
does not exist. If this infrastructure has already been applied, clone or
restore the current private state checkout in that location instead.

```sh
git init --initial-branch=main ../homelab-opentofu-state
```

The only state file to commit is
`../homelab-opentofu-state/trust-infrastructure.tfstate`.
This is the live, single-writer state. Use the designated checkout and
finish publishing any pending revision before applying from a different
workstation.

## 2. Enroll the state key

With the private wrapped-record submodule initialized and the YubiKey
connected, run:

```sh
make -C clusters/trust tofu-key-enroll
```

Touch the YubiKey for wrapping and again for independent recovery. The
helper generates 32 random bytes for AES-256-GCM and creates
`secrets/wrapped/trust-opentofu-state-r1.json` exclusively. The key ID is
`homelab/v1/trust/opentofu/state/infrastructure/r1`. For an existing record,
or an interrupted enrollment that may have written it, run:

```sh
make -C clusters/trust tofu-key-verify
```

Review and push the wrapped record to the private secrets repo, then
commit and push the updated submodule pointer to the parent repo before
depending on the key. Trust, OpenBao, and the UPS coordinator are
independent of this key-recovery path. The OpenTofu external key provider
supplies keys through the child process protocol and records only the
non-secret key ID in encryption metadata.

## 3. Validate, plan, and install

The validation command downloads and checks the chart and installs the
locked providers. It does not require a YubiKey touch or contact the cluster.

```sh
make -C clusters/trust tofu-validate
```

Before applying, confirm that `trust-cp1` is `Ready` and `trust-data` is
online and unlocked. The CSI driver uses the existing pool. Review the
plan with an attached YubiKey:

```sh
make -C clusters/trust tofu-plan
```

Expect the `openebs-zfs` namespace, the standalone `zfs-localpv` Helm
release, and the non-default `trust-zfs-rehearsal` StorageClass to be
created on the first run. The class uses `trust-data`, native ZFS
datasets, `WaitForFirstConsumer`, and `Delete` for the disposable test.
Check for unexpected changes before applying.

```sh
make -C clusters/trust tofu-apply
```

Review the new plan printed by apply and confirm it at the prompt.
Touch the YubiKey for the Talos admin identity and each OpenTofu key
request. Follow the HSM prompts in your terminal. Keep your finger off
the key during the no-touch check, tap when prompted, and lift your finger
when the helper confirms the touch. Initialization and planning can each
request the state key more than once. The operator helper keeps the
kubeconfig, working files, provider diagnostics and any failure-recovery
state in private verified tmpfs. Public provider packages are cached under `clusters/trust/bin/`
so they can execute even when tmpfs is mounted `noexec`. State and plan
encryption are enforced by the Trust root. Plans are reviewed in the
terminal.

After an apply, check the OpenTofu envelope without displaying the state.
This checks its on-disk format. The next OpenTofu plan checks authenticated
decryption.

```sh
python3 - ../homelab-opentofu-state/trust-infrastructure.tfstate <<'PYTHON'
import json
import sys
from pathlib import Path

state = json.loads(Path(sys.argv[1]).read_bytes())
if not all(state.get(name) for name in ("encrypted_data", "encryption_version", "meta")):
    raise SystemExit("Missing encrypted state envelope. Do not commit this state.")
print(f"Encrypted Trust state envelope, serial {state['serial']}")
PYTHON
```

Review and commit only the encrypted state file.

```sh
git -C ../homelab-opentofu-state status --short &&
  git -C ../homelab-opentofu-state add -- trust-infrastructure.tfstate &&
  git -C ../homelab-opentofu-state commit -m 'Update Trust infrastructure state'
```

Push after the private `simlun-ai/homelab-opentofu-state` repo and its
remote are ready. Keep routine `.backup` and lock files out of commits.
If an apply fails, inspect the encrypted state checkout for changes
before retrying. If a RAM recovery file is reported, keep the workstation
running and reconcile that file before another apply. Treat recovery
files as secret-bearing and keep them in RAM. Avoid `tofu state pull`
in normal operations because it prints decrypted state.

## 4. Verify and recover

Verify the CSI node plugin registered on `trust-cp1` and the controller
is ready before provisioning a test claim. Use the existing Trust
memory-only administration flow to create a disposable PVC with
`storageClassName: trust-zfs-rehearsal`. It will bind once a consumer pod
is scheduled. Write a fixture, replace the consumer, and verify that the
same claim serves the original bytes. Use Talos debug to inspect the
backing ZFS dataset and verify `encryption=aes-256-gcm`,
`encryptionroot=trust-data`, and the effective `compression` property.
Delete the test PVC and verify reclamation of its dataset.

To recover state, restore the most recent committed ciphertext to the
sibling checkout and recover the corresponding wrapped key generation.
Run `make -C clusters/trust tofu-key-verify` and
`make -C clusters/trust tofu-plan`. Review the plan against the live
cluster before applying, especially if restoring an older state revision.
Retain historical key generations needed by backed-up state. Preserve
`trust-data` and use the [Trust recovery runbook](../docs/installation/02-trust.md)
for the pool and its separate ZFS key.
