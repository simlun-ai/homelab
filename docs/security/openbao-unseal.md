# OpenBao unseal

**Unseal decision approved; implementation and restore verification pending.**

## Seal and wrapped material

Use OpenBao's Shamir seal with one share and a threshold of one.
Wrap the OpenBao-generated share using the
[v1 record format](security.md#challenges-derivation-and-wrapped-credentials)
under:

```text
homelab/v1/vault/openbao-unseal/share-1/r1
```

Keep the encrypted record in the repository and all four recovery USB
clones under the [storage policy](encrypted-record-storage.md). Any one
configured YubiKey can unwrap it; the four tokens provide redundancy.

## Operator-driven unseal

The workstation helper requires YubiKey touch, unwraps the share in
memory, and submits it to OpenBao over verified TLS. Follow the
[memory-only handling policy](security.md#secret-handling-boundary).
This is manual, operator-driven unseal; no auto-unseal is planned.

Preserve the corresponding unseal material for retained snapshots.
Validate restoration to both required recovery targets using that
material; exact initialization, restore, and unseal ordering remains
pending in [recovery procedures](recovery-procedures.md).

## Recovery administration

Unsealing does not grant administrative login. The proposed recovery
path uses a separately wrapped administration credential, accessible
without OpenBao. Its authentication method, identifier, permissions,
and lifecycle remain TBD.

## Remaining implementation work

- Implement initialization and memory-only wrapping of the generated share.
- Establish the encrypted-record filename and manifest entry.
- Implement and verify unseal through every token and the software fallback.
- Select and test recovery administration access.
- Test snapshot restoration with the corresponding unseal material.
