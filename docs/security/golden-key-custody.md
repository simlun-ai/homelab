# Golden-key custody

**Golden-1 custody, replication and independent replica retrieval verified 2026-11-04.**

Store each golden-key generation using **pass inside the offline level1vault
live OS**, in its persistent encrypted workspace/home. The initial item is
`yubikey/hsm/golden-1`; its plaintext is exactly one line of 40 hexadecimal
characters encoding 20 random bytes, preserving leading zeros. The generation
label matches wrapped records' `root_key` field. Keep descriptions in the runbook,
not as extra plaintext lines in the item.

[Level1vault's custody procedure](https://github.com/simlun-ai/level1vault/blob/main/docs/HSM.md)
owns checking for an existing entry, terminal pinentry, first-time insertion,
retrieval pipelines and workspace replication/retrieval acceptance. Assume pass
is configured; its decryption material must be usable independently of the HMAC
slot being programmed. Import code/wheels before handling secrets; never install
dependencies from the network during the live session.

Homelab-hsm owns random generation, strict streamed key input and token
programming/verification. Generate only when the stored generation is absent;
never replace it in response to a retrieval, write or verification failure.
Retrieve from pass for every programming command and the final verification.
Retain older generations while required wrapped records or backups depend on them.

Use this material for replacement tokens and emergency software recovery.
Decrypted keys follow the [memory-only policy](security.md#secret-handling-boundary).
Never include them in code or wrapped-record repositories. The encrypted pass
store and GnuPG decryption material need independently verified replication;
an active USB mirror alone is not an independent backup.

Verify the retrieved entry against the tokens before relying on it, comparing
HMAC responses only in memory. [Step 00](../installation/00-yubikey-setup.md) owns
the four-token ceremony and public results. The saved `golden-1` entry was
verified against all four tokens and the software fallback. The operator also
confirmed workspace replication and saved-entry retrieval/verification from
independent read-only replicas. This establishes custody acceptance for the
initial generation; future production-credential and service recovery drills
remain separate. Physical storage locations stay outside this repository.
