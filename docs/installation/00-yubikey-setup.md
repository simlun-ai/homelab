# 00 - YubiKey setup

**First implementation; physical programming and verification pending.**

Development checks cover the automated helper tests and a wheel-build/offline-install smoke test. The actual laptop, USB permissions, and all four tokens still need the trials below.

Configure and verify all four YubiKeys from a trusted Debian/Ubuntu laptop. Install and verify dependencies while the laptop is online, then make it air-gapped before handling the golden key. The [approved setup](../security/yubikey-setup.md) owns slot/settings; [Level 1](../security/golden-key-custody.md) owns golden-key custody. No production credential records are created in this step.

## Prerequisites

- The four labelled tokens, `key0` through `key3`, and access to Level 1.
- A trusted Debian/Ubuntu laptop with CPython 3.11–3.14 and a full repository clone. It can be online for the preparation below. Use a local console on bare metal; no terminal recording or clipboard manager during secret handling.
- Four recovery USBs with empty destination directories. Use the [existing recovery-clone policy](../security/encrypted-record-storage.md#recovery-usb-clones).

Commands below run from the repository root unless stated otherwise. The helper uses the scope's `bin/python` and checks installed versions against the offline bundle; it never falls back to global tools. The host Python used to create that environment is an explicit bootstrap prerequisite.

## 1. Install and verify dependencies — laptop online

Complete this on the setup laptop before accessing Level 1 or handling the golden key. Use a fresh checkout for the first tooling installation:

```sh
sudo apt-get update
sudo apt-get install python3 python3-venv python3-pip python3-dev build-essential swig pkg-config libpcsclite-dev make git
python3 -I -B scripts/yubikey_tools.py prepare
python3 -I -B scripts/yubikey_tools.py install
make -C support/yubikey test
```

Expected: preparation creates `wheelhouse/`, `requirements.lock`, and `bundle.json` under `support/yubikey/`. Installation checks their hashes and dependency consistency, then creates `bin/python`; the tests use disposable public keys and no hardware. The scope's [toolchain pins](../../support/yubikey/toolchain.yaml) select direct dependencies, and the generated bundle locks every resolved dependency plus the exact host runtime. Building `pyscard` needs the native prerequisites above even though this step uses USB OTP.

Record the printed bundle SHA-256 and retain the complete public tooling bundle for the recovery USBs. Any additional package installation or troubleshooting belongs in this online phase.

Grant the active local login access to the inventory's USB OTP devices:

```sh
sudo install -m 0644 support/yubikey/69-homelab-yubikey.rules /etc/udev/rules.d/69-homelab-yubikey.rules
sudo udevadm control --reload-rules
```

The rule applies when a token is next connected. Run the helpers as the local user, not through `sudo`.

## 2. Make the laptop air-gapped and prepare the session

Disconnect network cables and disable Wi-Fi/Bluetooth before opening Level 1 or entering the golden key. Keep the laptop disconnected throughout programming and verification, then:

```sh
sudo swapoff -a
sudo systemctl mask --runtime sleep.target suspend.target hibernate.target hybrid-sleep.target suspend-then-hibernate.target
ulimit -c 0
cat /proc/swaps
cat /sys/kernel/kexec_crash_loaded
```

Expected: `/proc/swaps` contains only its header; the crash-kernel value is `0`. If a crash kernel is loaded, disable crash dumping through the OS configuration and reboot before continuing. Keep the laptop awake, plugged into power, and offline until shutdown. Reapply these session settings after a reboot.

The helper also refuses active swap and redirected terminals, disables process core dumps/ordinary process-memory inspection, and disables SDK logging. Python cannot guarantee zeroization of every secret copy; process exit and final shutdown end the session. These checks do not attest the laptop's trustworthiness or air gap. Apply the full [memory-only policy](../security/security.md#secret-handling-boundary).

## 3. Establish the Level 1 record

Using your existing Level 1 process, create `golden-1` from **20 cryptographically random bytes** if it does not exist, or retrieve the existing generation. Preserve exactly 40 hexadecimal characters, including leading zeros, and verify that the offline record is backed up under the [custody policy](../security/golden-key-custody.md).

Generation and storage stay inside Level 1; the helper only consumes its record. Enter the key manually at the helper's hidden local prompts. Never put it in a shell command, environment variable, clipboard, checkout, transfer/recovery USB, or chat. Do not generate a replacement merely because programming or verification failed.

## 4. Inspect and program one token at a time

Connect only `key0`:

```sh
make -C support/yubikey inspect
make -C support/yubikey program LABEL=key0
```

Inspect prints firmware, serial where available, and slot occupancy. Compare the device with the [inventory](../inventory.md#security-keys). Stop on an unexpected device or occupied slot 1. The program command asks for the Level 1 key twice, then asks you to type `program key0 slot1` after checking the physical label. It refuses to overwrite slot 1 and never writes slot 2.

Expected: slot 1 is programmed, then verification alternates **do not touch** probes with explicit touch prompts. It compares three public 64-byte challenges with software HMAC in memory and prints a non-secret PASS. Responses and derived keys are never displayed. Source support covers firmware 2.2 onward; actual compatibility with both older Standard tokens must be proved here.

Remove the token and repeat those two commands for `key1`, `key2`, and `key3`, changing `LABEL`. If a token is already programmed or a run was interrupted after the write, use verification instead of programming again:

```sh
make -C support/yubikey verify LABEL=key0
```

## 5. Verify the complete set and offline record

Reopen the saved `golden-1` record from Level 1, then run:

```sh
make -C support/yubikey verify-set
```

Enter that saved value at the hidden prompts. Follow the remove/insert sequence for all four labels. The helper rejects repeated serials when available; where a serial is unavailable, distinct physical labels are the operator's check.

Expected: each token passes touch and HMAC checks. A fresh dummy credential wrapped with `key0` is unwrapped by all four tokens and the software fallback. The dummy record, payload, HMAC responses, and derived keys remain in process memory. A final PASS establishes agreement with the retrieved Level 1 record; it does not establish recovery of future production credentials.

## 6. Record results and prepare recovery kits

Record the tested Git commit, OS/Python version, bundle hash, date, and operator here. Add observed model/firmware/serial-to-label mappings to [inventory.md](../inventory.md#security-keys). Do not save terminal transcripts or secret test values.

| Token | Programmed | Individual checks | Cross-token checks |
| --- | --- | --- | --- |
| key0 | Pending | Pending | Pending |
| key1 | Pending | Pending | Pending |
| key2 | Pending | Pending | Pending |
| key3 | Pending | Pending | Pending |

For each paired recovery USB, use an empty destination. Replace `/media/RECOVERY` with that USB's mount point. Confirm the local clone is full, export its committed history, and copy the public tooling:

```sh
git rev-parse --is-shallow-repository
git bundle create /media/RECOVERY/homelab.bundle --all
git bundle verify /media/RECOVERY/homelab.bundle
git clone /media/RECOVERY/homelab.bundle /media/RECOVERY/homelab
mkdir /media/RECOVERY/yubikey-tools
cp -a support/yubikey/wheelhouse support/yubikey/requirements.lock support/yubikey/bundle.json /media/RECOVERY/yubikey-tools/
git -C /media/RECOVERY/homelab fsck --full
git -C /media/RECOVERY/homelab rev-parse HEAD
git -C /media/RECOVERY/homelab rev-parse --is-shallow-repository
sha256sum /media/RECOVERY/yubikey-tools/bundle.json
```

Both shallow-status checks must print `false`. Expected: a valid full clone at the intended commit and the recorded tooling-bundle hash. Inspect the clone's remote URL for embedded credentials. These clones initially contain no production wrapped records. Refresh them after test results or recovery-critical changes are committed.

For a later offline tooling reinstall, use `python3 -I -B scripts/yubikey_tools.py install --bundle /media/RECOVERY/yubikey-tools` from a fresh clone. That bundle requires its recorded distro release, architecture, ABI, and exact Python version; prepare a new bundle while online when changing runtimes.

- [ ] Record the real installation results and resolve failures.
- [ ] Prepare each token's full recovery USB clone and public tooling bundle; verify the recorded commit and bundle hashes offline.
- [ ] Verify Level 1 backup/retrieval and distribute the four token/USB pairs under the custody policy.

Shut down the air-gapped laptop before reconnecting anything networked. Later record/helper changes require kit refreshes. The [Emergency Recovery Guide](../emergency-recovery-guide.md) still has pending service-recovery work; these kits do not yet constitute a verified Vault recovery path.

## Failure actions

| Failure | Action |
| --- | --- |
| Tool installation or pin/hash mismatch | Resolve it during online preparation, before retrieving secrets. A changed runtime needs a newly prepared public bundle. |
| No token or multiple tokens | Connect one device, check its enabled OTP interface and local-seat USB permissions, then retry inspection. |
| Occupied slot 1 | Use `verify` with the existing Level 1 record. Resolve unexpected contents before any separate replacement procedure; there is no force-overwrite option. |
| Interrupted write, touch failure, or HMAC/unwrap mismatch | Remove/reinsert the token and run `verify`. Keep it marked unverified; report only the phase and public device metadata. Do not delete the Level 1 record, generate a new golden key, or continue to coordinator setup. |

## Upstream references

- [Pinned Yubico OTP implementation](https://github.com/Yubico/yubikey-manager/blob/5.9.2/yubikit/yubiotp.py): firmware support, fixed-length configuration, and HMAC operations.
- [Pinned Yubico USB OTP protocol](https://github.com/Yubico/yubikey-manager/blob/5.9.2/yubikit/core/otp.py): touch requests and cancellation.
- [Yubico Linux device permissions](https://github.com/Yubico/yubikey-manager/blob/5.9.2/doc/Device_Permissions.adoc).
