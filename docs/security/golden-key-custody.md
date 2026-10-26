# Golden-key custody

**Decision approved; backup and recovery verification pending.**

Store each golden-key generation in the existing **Level 1 Password
Management system**: air-gapped USB drives and computers already
replicated across multiple locations.

The computers receive their dependencies before becoming air-gapped for use.

Each entry contains:

- The actual 20-byte golden key encoded as exactly 40 hexadecimal
  characters, preserving leading zeros.
- Its generation label, matching the wrapped records' `root_key` field
  (initially `golden-1`).
- A brief description identifying it as the homelab HMAC-SHA1 foundation.

Retain older generations while required wrapped records or backups
depend on them.

Use this material for replacement-token programming and emergency
software recovery. Loading it onto a workstation follows the
[memory-only handling policy](security.md#secret-handling-boundary).
Never include it in any of the repositories.

Verify each stored entry against a configured YubiKey before relying
on it, comparing HMAC responses only in memory. The first verification
helper is documented in [step 00](../installation/00-yubikey-setup.md);
actual backup, retrieval, and device verification remain pending.

Level 1's internal procedures and physical locations are outside
this repository's scope.
