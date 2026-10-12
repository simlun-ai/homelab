# Credential catalogue

**Catalogue rules approved; concrete entries and implementation pending.**

The [YubiKey credential catalogue](yubikey.md) owns entries, identifiers,
and their metadata. This document defines how entries are finalized.

- Keep one wrapped record per independently managed credential, including
  one per ZFS encryption root.
- Map each exact identifier to its encrypted-record filename through the
  public manifest under `secrets/wrapped/`, following the
  [storage policy](encrypted-record-storage.md).
- Maintain each entry's metadata under the catalogue's
  [record requirements](yubikey.md#record-and-maintenance-requirements).
- Finalize identifiers when resource boundaries are known; retain
  explicit TBDs for missing node/pool names, ZFS encryption roots, Talos
  volume mappings, and bootstrap bundle contents.
- Keep every bootstrap/recovery credential accessible without the
  service it helps recover.

Concrete entries remain planned until configured and verified.
Manifest schema and tooling belong to
[helper implementation](helper-implementation.md).
