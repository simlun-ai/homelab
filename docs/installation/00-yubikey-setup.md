# 00 - YubiKey setup

**First implementation; physical programming and verification pending.**

Configure and verify all four YubiKeys from a trusted Debian/Ubuntu laptop. Install and verify dependencies while the laptop is online, then make it air-gapped before handling the golden key. The [approved setup](../security/yubikey-setup.md) owns slot/settings; [Level 1](../security/golden-key-custody.md) owns golden-key custody. No production credential records are created in this step.

## Prerequisites

- The four labelled tokens, `key0` through `key3`, and access to Level 1.
- A trusted Debian/Ubuntu laptop with CPython 3.13–3.14. It can be online for preparation. Use a local terminal without recording during secret handling.

After cloning, commands run from the repository root. Helpers use `support/yubikey/.venv/bin/python`; host Python creates the virtualenv and runs the standard-library key-generation example below.

## 1. Install and verify dependencies — laptop online

Complete this before accessing Level 1 or handling the golden key:

```sh
sudo apt install git
git clone https://github.com/simlun-ai/homelab.git
cd homelab
git submodule update --init --recursive -- tools/homelab-hsm
bash support/yubikey/install-system-dependencies.sh
make -C support/yubikey tools
make -C support/yubikey test
```

Expected: the idempotent script installs missing system packages and configures local-user USB access, requesting `sudo` when needed. `tools` uses standard `python3 -m venv`, `pip install -r` with [requirements.txt](../../support/yubikey/requirements.txt), plus the local project at `tools/homelab-hsm/homelab_secrets` (which owns token/crypto dependency pins), and `pip check`. Both setup commands can be rerun. The tests cover the parent and code repositories using disposable public keys and no hardware. Only the code submodule must be initialized before `tools` or `test`; token setup and tests do not require private records.

USB permissions apply when a token is next connected. Run the helpers as the local user, not through `sudo`. Finish any dependency troubleshooting while online.

## 2. Make the laptop air-gapped

Disconnect network cables and disable Wi-Fi/Bluetooth before opening Level 1 or entering the golden key. Keep the laptop disconnected throughout programming and verification.

The trusted laptop keeps its existing OS swap/suspend settings. The helper avoids secret files and output, disables its core dumps and SDK logging, and uses hidden prompts under the [secret-handling policy](../security/security.md#secret-handling-boundary).

## 3. Establish the Level 1 record

Using your existing Level 1 process, create `golden-1` from **20 cryptographically random bytes** if it does not exist, or retrieve the existing generation. Preserve exactly 40 hexadecimal characters, including leading zeros, and verify that the offline record is backed up under the [custody policy](../security/golden-key-custody.md).

Generation and storage stay inside Level 1; the helper only consumes its record. Enter the key manually at the helper's hidden local prompts. Never put it in a shell command, environment variable, clipboard, checkout, or chat. Do not generate a replacement merely because programming or verification failed.

### Generate a new golden key

If `golden-1` does not yet exist, on the trusted laptop, **after disconnecting it from all networks**, generate 20 cryptographically random bytes as 40 hexadecimal characters:

```sh
python3 -c 'import secrets; print(secrets.token_hex(20))'
```

Run this once, preserve the output in your offline Level 1 Password Management system, and use that same value for all four YubiKeys. The key appears in the terminal, so avoid terminal recording or output redirection.

## 4. Inspect and program one token at a time

Connect only `key0`:

```sh
make -C support/yubikey inspect
make -C support/yubikey program LABEL=key0
```

Inspect prints firmware, serial where available, and slot occupancy. Compare the device with the [inventory](../inventory.md#security-keys). Stop on an unexpected device. The program command asks for the Level 1 key twice, then asks you to type `program key0 slot2` after checking the physical label. By default it refuses occupied slot 2; slot 1 is never written.

Expected: slot 2 is programmed, then verification alternates **do not touch** probes with explicit touch prompts. It compares three public 64-byte challenges with software HMAC in memory and prints a non-secret PASS. Responses and derived keys are never displayed. Source support covers firmware 2.2 onward; actual compatibility with both older Standard tokens must be proved here.

If slot 2 already contains the golden key, or a run was interrupted after the write, use verification instead of programming again:

```sh
make -C support/yubikey verify LABEL=key0
```

To deliberately replace a different slot 2 configuration after checking its current use:

```sh
make -C support/yubikey replace LABEL=key0
```

This invokes `program --replace`. After the hidden key prompts, confirm the physical label and type `replace key0 slot2 and erase existing credential`. It overwrites the existing slot 2 credential, preserves slot 1, and immediately runs the same verification. A slot protected by an existing programming access code requires separate handling.

Remove the token and repeat inspection and the appropriate command for `key1`, `key2`, and `key3`, changing `LABEL` and the confirmation label.

## 5. Verify the complete set and offline record

Reopen the saved `golden-1` record from Level 1, then run:

```sh
make -C support/yubikey verify-set
```

Enter that saved value at the hidden prompts. Follow the remove/insert sequence for all four labels. The helper rejects repeated serials when available; where a serial is unavailable, distinct physical labels are the operator's check.

Expected: each token passes touch and HMAC checks. A fresh dummy credential wrapped with `key0` is unwrapped by all four tokens and the software fallback. The dummy record, payload, HMAC responses, and derived keys remain in process memory. A final PASS establishes agreement with the retrieved Level 1 record; it does not establish recovery of future production credentials.

## 6. Record results

Record the tested Git commit, OS/Python and installed package versions, date, and operator here. Add observed model/firmware/serial-to-label mappings to [inventory.md](../inventory.md#security-keys). Do not save terminal transcripts or secret test values.

| Token | Programmed | Individual checks | Cross-token checks |
| --- | --- | --- | --- |
| key0 | Pending | Pending | Pending |
| key1 | Pending | Pending | Pending |
| key2 | Pending | Pending | Pending |
| key3 | Pending | Pending | Pending |

Prepare replacement/recovery laptops using section 1 while online, then disconnect before handling the golden key. Rerun `tools` and `test` after selecting a different code-submodule version to refresh its package/dependencies and verify the [parent/library contract](../security/helper-implementation.md#coordinator-password-helper). Independent recovery-tool acquisition remains [pending](../security/recovery-procedures.md).

- [ ] Record the real installation results and resolve failures.
- [ ] Verify Level 1 backup/retrieval and keep the four tokens at separate locations under the custody policy.

Shut down the air-gapped laptop before reconnecting anything networked. The [Emergency Recovery Guide](../emergency-recovery-guide.md) still has pending service-recovery work; this setup does not yet constitute a verified Vault recovery path.

## Failure actions

| Failure | Action |
| --- | --- |
| Dependency installation or `pip check` failure | Resolve it during online preparation, before retrieving secrets; rerun system dependencies and `tools`. |
| No token or multiple tokens | Connect one device, check its enabled OTP interface and local-seat USB permissions, then retry inspection. |
| Occupied slot 2 | Use `verify` when it already holds the golden key. Use `replace` only after reviewing the existing credential and explicitly confirming its erasure. |
| Interrupted write, touch failure, or HMAC/unwrap mismatch | Remove/reinsert the token and run `verify`. Keep it marked unverified; report only the phase and public device metadata. Do not delete the Level 1 record, generate a new golden key, or continue to coordinator setup. |

## Upstream references

- [Pinned Yubico OTP implementation](https://github.com/Yubico/yubikey-manager/blob/5.9.2/yubikit/yubiotp.py): firmware support, fixed-length configuration, and HMAC operations.
- [Pinned Yubico USB OTP protocol](https://github.com/Yubico/yubikey-manager/blob/5.9.2/yubikit/core/otp.py): touch requests and cancellation.
- [Yubico Linux device permissions](https://github.com/Yubico/yubikey-manager/blob/5.9.2/doc/Device_Permissions.adoc).
