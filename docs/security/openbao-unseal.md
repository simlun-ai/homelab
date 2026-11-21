# OpenBao unseal

The [Trust operator runbook](../installation/trust-openbao-initialize.md) covers initialization and manual unseal. The operator verified both on the live staged server on 2026-11-21.

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
Validate restoration into a disposable second OpenBao instance on Trust
using that material. The exact initialization, restore, and unseal sequence
remains pending in [recovery procedures](recovery-procedures.md).

## Recovery administration

Initialization wraps the initial root token separately in
`secrets/wrapped/trust-openbao-initial-root-token-r1.json` under
`homelab/v1/trust/openbao-bootstrap/initial-root-token/r1`. This token is
for occasional manual bootstrap under the decision below.

Unsealing does not grant administrative login. The proposed recovery
path uses a separately wrapped administration credential, accessible
without OpenBao. Its authentication method, identifier, permissions,
and lifecycle remain TBD.

## Manual root-token use

**Decision (2026-11-21).** Retain the wrapped initial root token for occasional
manual bootstrap on the Trust operator workstation. Defer a separate operator
login. Recover the token with a YubiKey and keep it in memory for the duration
of the task. The initial root token does not expire and grants unrestricted
OpenBao access.

Use dedicated, scoped credentials for the R2 backup job, External Secrets
Operator, and Talos KMS adapter. Revisit revoking the initial root token after
the R2 snapshot and restore rehearsal establishes a verified recovery path.
OpenBao supports generating a fresh root token with the unseal share for
emergency access. The recovery administration design remains open.

See [OpenBao token guidance](https://openbao.org/docs/concepts/tokens/) and
the [snapshot and restore milestone](../installation/trust-openbao-backups.md).

## Remaining implementation work

- Implement and verify unseal through every token and the software fallback.
- Select and test recovery administration access.
- Test snapshot restoration with the corresponding unseal material.
