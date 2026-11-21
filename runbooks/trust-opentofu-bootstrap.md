# Trust OpenTofu bootstrap

Trust's first OpenTofu root installs the OpenEBS ZFS LocalPV 2.11.2 driver
and a disposable-test StorageClass on the existing `trust-data` pool.
The deployment uses OpenTofu 1.13.9, the locked Helm and Kubernetes
providers, and the upstream chart whose SHA-256 is pinned in
[`zfs-localpv.json`](../clusters/trust/tofu/zfs-localpv.json).
The cluster-specific [Helm values](../clusters/trust/helm/values/infrastructure/zfs-localpv.yaml)
configure the host ZFS binary, kubelet path, and placement on `trust-cp1`.
The same infrastructure root also owns [Trust cert-manager and its ACME issuers](../docs/installation/trust-cert-manager.md). The [OpenBao workload](../docs/installation/trust-openbao.md) uses a separate root and state.

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

The state file for this infrastructure root is
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

The validation command downloads and checks the charts and installs the
locked providers. It does not require a YubiKey touch or contact the cluster.

```sh
make -C clusters/trust tofu-validate
```

Trust's only node runs both the control plane and workloads. Its
`KubeNodeConfig` patch removes the standard control-plane scheduling
taint. The install and rebuild configuration includes the patch. For an
already installed node that still has the taint, preview the live change.

```sh
make -C clusters/trust scheduling-preview
```

Confirm that the preview removes only
`node-role.kubernetes.io/control-plane: NoSchedule` from the node's
taints. Apply it live.

```sh
make -C clusters/trust scheduling-apply
```

Use the Trust administration flow to confirm the taint is absent in the
Kubernetes node's `spec.taints`. If recovering from the first failed
LocalPV apply, recover the state below before running another OpenTofu
plan or apply.

Before applying, confirm that `trust-cp1` is `Ready` and `trust-data` is
online and unlocked. The CSI driver uses the existing pool. Review the
plan with an attached YubiKey. First prepare the [wrapped cert-manager token](../docs/installation/trust-cert-manager.md#prepare-the-wrapped-token), which plan and apply now recover automatically:

```sh
make -C clusters/trust tofu-plan
```

Expect the `openebs-zfs` namespace, the standalone `zfs-localpv` Helm
release, and the non-default `trust-zfs-rehearsal` StorageClass to be
created on the first run. The class uses `trust-data`, native ZFS
datasets, `WaitForFirstConsumer`, and `Delete` for the disposable test.
The [cert-manager runbook](../docs/installation/trust-cert-manager.md#review-and-apply-trust-infrastructure) lists that installation's additions. Check for unexpected changes before applying.

```sh
make -C clusters/trust tofu-apply
```

Review the new plan printed by apply and confirm it at the prompt.
Touch the YubiKey once to recover the OpenTofu state key and once for the
Talos admin identity, plus one touch for the cert-manager token. Keep your finger off the key during each no-touch
check, tap when prompted, and lift your finger when the helper confirms
the touch. OpenTofu reuses the recovered state key for this invocation
over a private Unix socket in the verified RAM workspace. The helper
keeps the kubeconfig, working files, provider diagnostics, and any
failure-recovery state in private verified tmpfs. Public provider packages are cached under `clusters/trust/bin/`
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
If an apply fails, inspect the encrypted state checkout for changes before
retrying. If the helper prints a retained `errored.tfstate` path, keep the
workstation running and recover the state before another plan or apply.
Run the following with the exact RAM path printed by the helper.

```sh
make -C clusters/trust tofu-state-recover \
  TOFU_RECOVERY_FILE=/dev/shm/trust-tofu-recovery-REPLACE/errored.tfstate
```

The helper checks that the recovery file resides on tmpfs and is a private
operator-owned file. If the emergency snapshot is encrypted, the helper
opens a copy through a separate temporary backend and captures the
decrypted state in memory. It passes the state to the usual encrypted
backend with OpenTofu's lineage and serial checks enabled. Only the
wrapped state key is needed. Leave the RAM recovery copy
in place until the encrypted state is verified and the next plan accounts
for the resources left by the failed apply. Avoid `tofu state pull` during
normal operations because it prints decrypted state.

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

## 5. Verify the production retention policy

The Trust infrastructure root defines the non-default
`trust-zfs-retain` StorageClass for OpenBao's Raft data and other
workloads that explicitly select it. It provisions ZFS filesystems on
`trust-data` with `WaitForFirstConsumer`, `Retain`, and explicit
`compression=lz4`. The backing dataset inherits encryption from
`trust-data`.

For an existing Trust installation whose latest plan reports no changes,
review a new `make -C clusters/trust tofu-plan` for exactly one addition,
`kubernetes_storage_class_v1.zfs_retain`. Apply it with the same
`tofu-apply` workflow and commit the updated encrypted state.

Rehearse the policy with a disposable claim before pointing OpenBao at it.

1. In a temporary namespace, create a scratch PVC that explicitly selects
   `trust-zfs-retain`. Mount it from a consumer pod and write a non-secret
   fixture. Record the bound PV, its CSI volume handle, and the matching
   ZFS dataset.
2. Use Talos debug to confirm `encryption=aes-256-gcm`,
   `encryptionroot=trust-data`, and `compression=lz4`.
3. Delete the consumer and the scratch claim. Confirm that the PV moves to
   `Released` and that the recorded ZFS dataset is still present.
4. Confirm the released PV and dataset identities before deliberately
   reclaiming that disposable test volume. Verify both are gone, then
   delete the temporary namespace.

Retained local volumes still depend on the Pi and mirror. The planned
[OpenBao Raft snapshots](../docs/backup-and-restore.md#openbao-online-backups)
cover recovery from their loss.
