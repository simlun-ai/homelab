# YubiKey Credential Catalogue

**Initial setup/wrapping helpers implemented; physical programming and verification pending.** Production lookup identifiers remain proposed and production credential records are not implemented.

This document owns the lookup catalogue. Hardware inventory belongs in [inventory.md](../inventory.md#security-keys); golden-key custody, secret handling, and encryption policy belong in [security.md](security.md); recovery requirements belong in [backup-and-restore.md](../backup-and-restore.md).

## Model

The four YubiKeys act as interchangeable mini HSMs, each holding the same 20-byte golden key and requiring touch for HMAC-SHA1 challenge-response. The [approved setup](yubikey-setup.md) selects OTP slot 1 and the existing labels `key0` through `key3`; programming and verification remain pending.

The logical key-value store consists of:

- A public identifier selecting a credential.
- A YubiKey response used to derive its wrapping key.
- An authenticated encrypted record containing the credential.

The token stores the golden key. Credential records live in the repository and its recovery USB clones under the [storage policy](encrypted-record-storage.md). Retrieving a wrapped credential requires both a working token and its encrypted record.

[HMAC-SHA1 challenge-response](https://developers.yubico.com/Developer_Program/Guides/Touch_triggered_OTP.html) accepts challenges up to 64 bytes and returns a deterministic response for the same challenge and secret. It does not itself encrypt or store arbitrary credential values.

## Identifier and challenge format

```text
homelab/v1/<scope>/<purpose>/<resource>/r<generation>
```

| Field | Meaning |
| --- | --- |
| `v1` | Lookup-protocol version. |
| `scope` | Cluster, supporting host, or recovery scope. |
| `purpose` | Distinct use, such as `zfs`, `openbao-unseal`, or `dns-api`. |
| `resource` | Stable resource identifier; may contain multiple path segments. |
| `r<generation>` | Wrapping-key generation, starting at `r1`. |

Identifiers use lowercase ASCII letters, digits, hyphens, and `/`, with nonempty path segments. No whitespace, implicit case conversion, or trailing newline. Preserve identifiers when moving storage or renaming hosts.

V1 challenge construction:

```text
challenge = ASCII(lowercase_hex(SHA256(ASCII(identifier))))
```

This produces exactly 64 challenge bytes. Configure matching fixed-length processing on all four tokens and verify it against the software fallback. [Yubico documents](https://developers.yubico.com/yubikey-personalization/Manuals/ykpersonalize.1.html) the HMAC and touch flags for firmware 2.2 and later; actual device verification remains required.

The raw response feeds HKDF-SHA-256 and AES-256-GCM using the [v1 encrypted-record format](security.md#challenges-derivation-and-wrapped-credentials). That section owns derivation, authenticated metadata, revision/rotation rules, and validation. The initial shared implementation is exercised by [step 00](../installation/00-yubikey-setup.md); production consumers remain pending.

The implemented setup helper reserves `homelab/v1/setup/verification/cross-token/r1` for an in-memory dummy credential under `golden-1`. It is not a production credential or persisted record.

The examples below omit the common `homelab/v1/` prefix.

## Direct YubiKey lookup catalogue

These identifiers propose coverage for the credential roles already documented in the repository.

| Identifier suffix | Protected material | Consumer |
| --- | --- | --- |
| `vault/openbao-unseal/share-1/r1` | OpenBao-generated unseal share; one share, threshold one under the [unseal policy](openbao-unseal.md). | Workstation unseal/restore helper. |
| `vault/kms/<node-id>/r1` | Random 32-byte node KMS key protecting Talos system-volume unlock payloads under the [two-layer design](helper-implementation.md#vault-kms-two-layers). Node mapping TBD. | Coordinator bootstrap KMS. |
| `support-vault-backup/dns-api/cloudflare/r1` | DNS API credential for independent KMS DNS-01 renewal. | Coordinator ACME integration. |
| `support-vault-backup/tls-private-key/kms/r1` | Coordinator KMS TLS private key. | Coordinator TLS service. |
| `support-vault-backup/acme-account/kms/r1` | ACME account private key and required account secrets. | Coordinator ACME integration. |
| `recovery/r2/openbao-restore/r1` | Independently recoverable R2 download credentials. | Snapshot restore helper. |
| `recovery/backup-decryption/openbao/r1` | Additional snapshot-decryption material, **if additional encryption is selected**. | Snapshot restore helper. |
| `vault/talos/bootstrap/r1` | Secret-bearing Talos bootstrap material; bundle boundaries TBD. | Vault bootstrap/rebuild helper. |
| `vault/talos/administration/r1` | Talos administration credentials. | Operator tooling. |
| `vault/kubernetes/administration/r1` | Kubernetes administration credentials. | Operator tooling. |

KMS authority and coordinator credentials are supplied from the workstation over SSH under the [session policy](coordinator-sessions.md): KMS expires after one hour; DNS, TLS, and ACME plaintext lasts for the coordinator process lifetime.

The selected Shamir seal uses an unseal share, not auto-unseal recovery keys. Recovery administration access is separate and remains TBD in the [unseal policy](openbao-unseal.md).

## Manual ZFS keys

Use one record per ZFS encryption root:

```text
homelab/v1/<scope>/zfs/<node-id>/<pool>/<root-id>/r1
```

`<root-id>` identifies the actual encryption root. The inventory establishes pool names, but dataset/zvol encryption boundaries remain TBD.

| Scope / node | Pool | Lookup suffix |
| --- | --- | --- |
| Vault / node ID TBD | Pool name TBD | `vault/zfs/<node-id>/<pool>/<root-id>/r1` |
| Backup / node ID TBD | Pool name TBD | `backup/zfs/<node-id>/<pool>/<root-id>/r1` |
| Metal / worker1 | `immich` | `metal/zfs/worker1/immich/<root-id>/r1` |
| Metal / worker1 | `photos` | `metal/zfs/worker1/photos/<root-id>/r1` |
| Metal / worker1 | `media` | `metal/zfs/worker1/media/<root-id>/r1` |
| Metal / worker2 | `dump` | `metal/zfs/worker2/dump/<root-id>/r1` |
| Metal / worker2 | `nas` | `metal/zfs/worker2/nas/<root-id>/r1` |
| Metal / worker3 | `bitcoin` | `metal/zfs/worker3/bitcoin/<root-id>/r1` |
| Metal / worker4 | `nvr` | `metal/zfs/worker4/nvr/<root-id>/r1` |
| Legacy / old NAS | Pool name TBD | `legacy/zfs/old-nas/<pool>/<root-id>/r1` |

These records wrap ZFS keys for the manual unlock helper. Pool preparation and repair remain manual.

Pi and Metal `piraeus` storage also require encryption, but their key-delivery scheme is unresolved. Direct YubiKey identifiers must be added if that scheme requires them.

## Secrets protected through OpenBao

These inherit YubiKey protection through wrapped OpenBao unseal material. Their normal retrieval uses OpenBao.

| Material | Retrieval/use |
| --- | --- |
| Backup, Pi, and Metal Talos system-volume unlock material | Python KMS adapter using OpenBao transit. |
| Transit keys and required historical versions | Retained in OpenBao and recoverable snapshots. |
| Application/service credentials | OpenBao reads, including External Secrets Operator integration. |
| Published certificates and private keys | cert-manager PushSecret into OpenBao; dependent clusters pull them. |

OpenBao mount names, secret paths, transit-key names, and authentication mappings are not yet defined. Add their exact references here when established.

## Bootstrap coverage still to resolve

Specify storage, delivery, and any direct lookup identifiers for:

- Vault cert-manager DNS/ACME credentials.
- R2 upload and OpenBao snapshot-job credentials.
- KMS adapter authentication and TLS bootstrap material.
- OpenBao recovery administration access.
- OpenTofu state-encryption and backend credentials.
- UPS coordinator management/shutdown credentials.
- YubiKey programming access codes are deferred to [future improvements](../future.md).

Vault bootstrap material must remain accessible without its own OpenBao instance.

## Record and maintenance requirements

**Catalogue rules approved; production entries and consumer integrations pending.**

- Keep one wrapped record per independently managed credential, including one per ZFS encryption root.
- Map exact identifiers to encrypted-record filenames through the public manifest under `secrets/wrapped/`, following the [storage policy](encrypted-record-storage.md). Manifest schema and tooling belong to [helper implementation](helper-implementation.md).
- Finalize identifiers when resource boundaries are known. Keep missing node/pool names, ZFS encryption roots, Talos volume mappings, and bootstrap bundle contents explicitly TBD.
- Keep every bootstrap/recovery credential accessible without the service it helps recover.

Concrete entries remain planned until configured and verified.

Each registered credential needs its exact identifier, consumer, encrypted-payload reference, public protocol parameters, root-key and wrapping-context generations, record revision, recovery dependency, and status: planned, configured, or verified.

Record identifiers and metadata only. Never record golden-key bytes, HMAC responses, derived keys, or plaintext credentials.

Retain required older generations and payloads until migration and restore tests pass. Public protocol metadata must also appear in every standalone [Emergency Recovery Guide](../emergency-recovery-guide.md); the paired USB holds the full repository clone, including wrapped records, under the [storage policy](encrypted-record-storage.md).
