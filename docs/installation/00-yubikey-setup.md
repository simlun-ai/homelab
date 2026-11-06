# 00 - YubiKey setup

**Completed: physical programming, verification and replica-retrieval acceptance confirmed 2026-11-04.**

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
Remove your finger during the two-second pause before each no-touch probe.
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
| key0 | PASS | PASS | PASS |
| key1 | PASS | PASS | PASS |
| key2 | PASS | PASS | PASS |
| key3 | PASS | PASS | PASS |

Acceptance completed on 2026-11-04 in the offline level1vault session, using
Python 3.13.5 and the updated installed HSM helper. All four tokens passed
three 44-byte HMAC/software comparisons, no-touch/touch checks, and
`verify-set`: each unwrapped the shared in-memory dummy record, and the software
fallback agreed. The operator subsequently confirmed workspace replication and
saved-entry retrieval/verification from independent read-only replicas.

- [x] Verify real USB access and GnuPG pinentry inside simlun's live tmux session.
- [x] Record real programming/touch/verification results for every token.
- [x] Follow level1vault's [replication and retrieval acceptance](https://github.com/simlun-ai/level1vault/blob/main/docs/HSM.md#replication-and-acceptance).

Device firmware and serial mappings are recorded in [inventory](../inventory.md#security-keys).
The fixes used were homelab-hsm [#7](https://github.com/simlun-ai/homelab-hsm/pull/7)
and [#8](https://github.com/simlun-ai/homelab-hsm/pull/8). Exact tested checkout
SHAs, live-image build ID, full installed package versions and replica checkpoint
IDs were not captured in this acceptance record. This does not establish
recovery of future production credentials or deployed services.

Ongoing custody: keep tokens and independent workspace copies at separate
locations, retain required generations, and repeat retrieval checks after changes.
Physical locations remain outside this repository.

Exit all panes and follow `start`'s export and poweroff prompts. The
[Emergency Recovery Guide](../emergency-recovery-guide.md) still has pending
service-recovery work; this ceremony is not a verified Trust recovery path.

## Failure actions

| Failure | Action |
| --- | --- |
| Offline installation fails | Stop before retrieving the key. Prepare corrected code/wheels or OS on the online workstation, transport them and retry offline. |
| pass retrieval or pinentry fails | Check the configured store, GnuPG identity and terminal using level1vault's procedure. Do not replace the entry. |
| No token, multiple tokens or permission failure | Connect one expected device; check enabled OTP interface and simlun's device-group access. |
| Occupied slot 2 | Verify if it holds the same key; replace only after reviewing its use and confirming erasure. |
| Interrupted write, touch failure, HMAC or unwrap mismatch | Reinsert and verify using the saved entry. Keep it marked unverified; report only public metadata and phase. Do not regenerate or continue coordinator setup. |

## Firmware 2.2 compatibility update

A physical run on `key3` (firmware 2.2.3, serial 1020513) reported a successful
slot 2 write but failed software HMAC comparison, including after reinsertion
without the cancelled no-touch probe. The old helper disabled `HMAC_LT64`,
which is affected by a documented firmware 2.2 bug. After enabling `HMAC_LT64`
and using 44-byte challenges, key3 passed programming verification, a separate
verification, and the full cross-token set check.

Use the updated homelab-hsm checkout and its rebuilt offline bundle. All tokens
must use `HMAC_LT64` and the new 44-byte challenge protocol described in
[yubikey.md](../security/yubikey.md). Keep the existing `yubikey/hsm/golden-1`
entry: do not generate or replace it to resolve this failure. For each occupied
slot 2 programmed with the old helper, use the existing explicit `program
--replace` procedure, confirm the physical label, and repeat verification and
`verify-set`. Slot 1 remains untouched. This updated configuration passed
physical verification on all four devices.

The v1 challenge definition was updated in place before real credential use.

Firmware 5.2.4 on key1 intermittently returned a response during the next
no-touch probe after a successful touched request. Prompting finger removal and
waiting two seconds before each probe resolved the observed failure; the installed
fix passed on key1 and in the full set check. The underlying sensor/firmware
mechanism remains unconfirmed. The probe still requires touch-needed status
and rejects immediate responses and unconfirmed timeouts.
