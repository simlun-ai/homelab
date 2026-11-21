# OpenBao unseal

The [Trust operator runbook](../installation/trust-openbao-initialize.md) covers initialization and manual unseal. Live verification is pending.

## Seal and wrapped material

Use OpenBao's Shamir seal with one share and a threshold of one.
Wrap the OpenBao-generated share using the
[v1 record format](security.md#challenges-derivation-and-wrapped-credentials)
under:

```text
homelab/v1/trust/openbao-unseal/share-1/r1
```

Keep `secrets/wrapped/trust-openbao-unseal-share-1-r1.json` in the private records repository under the [storage policy](encrypted-record-storage.md). Any one
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

Initialization wraps the initial root token separately in
`secrets/wrapped/trust-openbao-initial-root-token-r1.json` under
`homelab/v1/trust/openbao-bootstrap/initial-root-token/r1`. This token is
for bootstrap administration and is held until replacement access is verified.

Unsealing does not grant administrative login. The proposed recovery
path uses a separately wrapped administration credential, accessible
without OpenBao. Its authentication method, identifier, permissions,
and lifecycle remain TBD.

## Remaining implementation work

- Verify initialization, wrapping, and unseal on Trust.
- Implement and verify unseal through every token and the software fallback.
- Select and test recovery administration access.
- Test snapshot restoration with the corresponding unseal material.
