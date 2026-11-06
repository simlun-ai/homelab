# Trust cluster

Independent foundational Kubernetes cluster, initially a single control-plane
node (`trust-cp1`, `10.10.0.10`). See the
[installation roadmap](../../docs/installation/02-trust.md).

## Native Talos patches and committed public render

Source fragments live in `talos/patches/`: cluster-wide documents, optional
control-plane documents, and `nodes/trust-cp1/`. Each file owns **one distinct
native Talos configuration document** (`apiVersion`, `kind`, optional `name`).
We do not maintain a second node inventory schema or implement Talos patch
merging ourselves.

```sh
make -C clusters/trust render
make -C clusters/trust check-rendered
```

Commit the regenerated `talos/rendered/trust-cp1.yaml` with its source patch
edits. CI byte-compares the regenerated output and rejects duplicate document
identities and common secret-bearing fields. This is a defense-in-depth guard,
not a substitute for reviewing content before committing it.

**The rendered bundle is deliberately NOT apply-ready.** It contains exactly
the authored public documents (without Talos-generated defaults, PKI, secrets,
installation disks, early boot configuration or KMS). Later, pinned Talos
tooling will build the complete native machine config using the same patches
and independently recoverable secrets **in memory only**, and validate before
applying. Never commit or persist that complete config on workstation disk.

The Raspberry Pi `eth0` interface name and UEFI behavior remain unverified.
Do not apply this partial public bundle to a node.
