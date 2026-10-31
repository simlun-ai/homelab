# 00 - YubiKey setup

**Implementation available; physical programming and verification pending.**

Configure the four labelled tokens `key0` through `key3` inside an offline
[level1vault](https://github.com/simlun-ai/level1vault) live OS session. The
[approved setup](../security/yubikey-setup.md) owns the settings; the
[custody policy](../security/golden-key-custody.md) owns generation retention.
No production credential records are created in this step.

## 1. Enter the offline workspace and prepare tools

Boot level1vault with networking disconnected and use `start 1` (or the active
pair number). Work as simlun inside its tmux session. Assume `pass` is already
configured in the persistent home. Import the separately prepared repositories
using [level1vault Git transport](https://github.com/simlun-ai/level1vault/blob/main/docs/GIT-BUNDLES.md):

```sh
sudo workspace-transport-import 1
workspace-transport-import-git-bundles /mnt/workspace/inbox/<delivery>/git-bundles
```

Replace `<delivery>` with the reported directory. The checkouts are
`/mnt/workspace/git/homelab` and `/mnt/workspace/git/homelab-hsm`. Token setup uses
the standalone HSM checkout; neither the code nor private-records submodule needs
initializing. No clone, apt or online pip command runs in this session.

```sh
python3 -B /mnt/workspace/git/homelab-hsm/homelab_secrets/scripts/offline.py \
  install --venv /mnt/workspace/venvs/homelab-hsm
source /mnt/workspace/venvs/homelab-hsm/bin/activate
homelab-hsm --help
```

The installer verifies the committed wheels and runs hardware-free tests. Its
external environment leaves both imported repositories clean for future updates.
Reinstall after importing updated HSM code. Record both Git revisions used; this
standalone ceremony does not select its tools through homelab's submodule pin.

## 2. Establish or retrieve golden-1

Follow [level1vault's pass custody procedure](https://github.com/simlun-ai/level1vault/blob/main/docs/HSM.md#establish-the-stored-generation-once).
It owns terminal pinentry setup, checking for an existing entry and first-time
generation directly into `pass`. The item is **`yubikey/hsm/golden-1`**, containing
only 40 hex characters representing 20 random bytes, including leading zeros.

Do not generate a replacement after an installation, retrieval, programming or
verification failure. Never display, copy/paste or manually transcribe the key.
Use a local unrecorded terminal with shell tracing disabled. Enable `pipefail`
and stop on every failed pipeline. Keep the session offline throughout.

## 3. Inspect and program one token at a time

Connect only `key0`, then inspect it:

```sh
homelab-hsm inspect
```

Compare firmware, serial where available and slot occupancy with the
[inventory](../inventory.md#security-keys). Stop on an unexpected device.
Program from the saved entry using level1vault's [programming pipeline](https://github.com/simlun-ai/level1vault/blob/main/docs/HSM.md#program-and-verify-from-the-saved-entry)
and `homelab-hsm program --label key0`.

The CLI reads the key from stdin and physical confirmation from `/dev/tty`.
Type `program key0 slot2` only after checking the label. It refuses occupied
slot 2 by default and never writes slot 1. Programming is followed by three
public-challenge HMAC comparisons and alternating no-touch/touch checks.
Responses and derived keys remain in memory; only public results are printed.

If slot 2 already holds the key, or a write was interrupted, retrieve the same
entry and pipe it to `homelab-hsm verify --label key0`. For deliberate erasure
of a different slot 2 credential, use `homelab-hsm program --label key0 --replace`
and type `replace key0 slot2 and erase existing credential`. A programming access
code requires separate handling. Full CLI behavior belongs to
[homelab-hsm](https://github.com/simlun-ai/homelab-hsm/blob/main/homelab_secrets/SETUP.md).

Remove the token and repeat for `key1`, `key2` and `key3`, changing the label.
Verify actual compatibility with both older Standard tokens; software tests do
not establish hardware support.

## 4. Verify the complete set and stored entry

Retrieve the saved entry afresh and pipe it to:

```sh
homelab-hsm verify-set --labels key0 key1 key2 key3
```

This command requires piped key input; use the complete pipeline from the
[level1vault runbook](https://github.com/simlun-ai/level1vault/blob/main/docs/HSM.md#program-and-verify-from-the-saved-entry).
Follow its removal, insertion, label and touch prompts. Repeated serials are
rejected when available; otherwise check distinct physical labels yourself.
All four devices and software must unwrap the same disposable in-memory record.
PASS establishes agreement with the retrieved entry, not recovery of future
production credentials.

## 5. Record results, replicate and finish

Record both tested Git revisions, OS/Python/package versions, date and operator.
Update [inventory](../inventory.md#security-keys) with observed model, firmware
and serial-to-label mappings. Never save transcripts or secret test values.

| Token | Programmed | Individual checks | Cross-token checks |
| --- | --- | --- | --- |
| key0 | Pending | Pending | Pending |
| key1 | Pending | Pending | Pending |
| key2 | Pending | Pending | Pending |
| key3 | Pending | Pending | Pending |

- [ ] Verify real USB access and GnuPG pinentry inside simlun's live tmux session.
- [ ] Record real programming/touch/verification results for every token.
- [ ] Follow level1vault's [replication and retrieval acceptance](https://github.com/simlun-ai/level1vault/blob/main/docs/HSM.md#replication-and-acceptance).
- [ ] Keep tokens at separate locations under the custody policy.

Exit all panes and follow `start`'s export and poweroff prompts. The
[Emergency Recovery Guide](../emergency-recovery-guide.md) still has pending
service-recovery work; this ceremony is not a verified Vault recovery path.

## Failure actions

| Failure | Action |
| --- | --- |
| Offline installation fails | Stop before retrieving the key. Prepare corrected code/wheels or OS on the online workstation, transport them and retry offline. |
| pass retrieval or pinentry fails | Check the configured store, GnuPG identity and terminal using level1vault's procedure. Do not replace the entry. |
| No token, multiple tokens or permission failure | Connect one expected device; check enabled OTP interface and simlun's device-group access. |
| Occupied slot 2 | Verify if it holds the same key; replace only after reviewing its use and confirming erasure. |
| Interrupted write, touch failure, HMAC or unwrap mismatch | Reinsert and verify using the saved entry. Keep it marked unverified; report only public metadata and phase. Do not regenerate or continue coordinator setup. |
