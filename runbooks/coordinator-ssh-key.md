# Shared coordinator SSH key

**Workflow implemented; production key generation and Pi verification pending.**
All three coordinators use one repository-owned, randomly generated Ed25519
identity for `administrator`. Its OpenSSH private key has no passphrase;
YubiKey wrapping protects its persisted copy. Only the public key is installed
on the Pis. This identity is separate from the key used to access GitHub.

## Generate once

Use the workstation/token prerequisites and memory handling from the
[password runbook](coordinator-passwords.md#prepare). Then, from the repo root:

```sh
make -C support/ups ssh-key-create
```

Touch when prompted. The helper generates in memory, wraps and verifies the
private key, then writes only:

- `secrets/wrapped/coordinators-ssh-ed25519.json`: authenticated ciphertext.
- `support/ups/coordinator_ed25519.pub`: the public key, safe to commit.

Commit both and refresh the four recovery USB clones. The public
[manifest](../secrets/wrapped/manifest.json) reserves the wrapped record;
filenames are absent until you generate them with your token. Creation refuses
to overwrite either file. Reuse this identity when reinstalling a coordinator.

## Load before management operations

Use a local OpenSSH agent on the trusted workstation, not a forwarded agent or
an agent that persists imported private keys. If the shell does not already have
a local agent, start one in that shell:

```sh
eval "$(ssh-agent -s)"
```

Then:

```sh
make -C support/ups ssh-key-load
make -C support/ups bootstrap HOST=ups-aux
```

Loading unwraps the private key in memory, checks it matches the committed
public key, and pipes it directly to `ssh-add -t 1h -`. There is no decrypted
private-key file. The helper verifies that the agent can sign with the key.
The agent retains it for **one hour**; touch is needed to unwrap/load, not for
each SSH connection. Reload after expiration. This lifetime is independent of
any future KMS authorization window; unloading does not terminate existing SSH
sessions or KMS authority.

Ansible's Make targets and password delivery check the loaded identity before
connecting. Ansible selects the `.pub` file as its identity reference; OpenSSH
uses the corresponding private key from the agent. No private file is needed,
and agent forwarding is disabled. Avoid other `IdentityFile` directives for
these hosts in workstation SSH config. Direct playbook invocations bypass the
Make preflight, so use the documented Make commands.

After the work:

```sh
make -C support/ups ssh-key-unload
```

This removes only the coordinator identity from the selected agent. If you
started a dedicated agent, `eval "$(ssh-agent -k)"` also stops it. The workstation
memory-handling requirements apply to the agent for its entire lifetime, not
just the short-lived unwrap helper. Agent access permits signing while loaded;
unplugging the YubiKey does not remove that access.

## Authorize on the Pis

For new cards, select `support/ups/coordinator_ed25519.pub` in Imager's
public-key-only SSH setup. Follow the [base runbook](ups-coordinator-base-setup.md)
for host-key verification, bootstrap and hardening. Bootstrap manages
`administrator`'s complete `authorized_keys` file with this single public key.

For an already installed Pi, load the new key, then use your still-working old
SSH access to append the public key:

```sh
ssh-copy-id -i support/ups/coordinator_ed25519.pub administrator@ups-aux
```

Keep the old administrative session open. Test a **new** connection using only
the new identity and the independently verified host key:

```sh
ssh -F /dev/null -o StrictHostKeyChecking=yes -o BatchMode=yes \
  -o IdentitiesOnly=yes -o ForwardAgent=no \
  -i support/ups/coordinator_ed25519.pub administrator@ups-aux true
```

That test ignores workstation SSH aliases; substitute the verified address if
DNS does not resolve the hostname, and trust its host key first. Only after this
succeeds, run `make -C support/ups bootstrap HOST=ups-aux`: it replaces the old
authorized keys with the repository key. Test another new connection before
closing the old session. Repeat one coordinator at a time for `ups-pi` and
`ups-metal`. No remote keys are changed by generation or agent loading.

## Recovery

- Missing/expired agent identity: start/select the local agent and load again.
- Missing public file with intact ciphertext: `make -C support/ups ssh-key-public`
  reconstructs it through the YubiKey; it will not overwrite an existing file.
- Mismatched public/private files: restore a matching pair from trusted Git
  history or a recovery clone. Do not generate a replacement by accident.
- Interrupted creation: ciphertext is written first; recover its public key
  only if the record authenticates. Preserve/inspect incomplete files before
  removing them. Interrupted loading may have succeeded; check or unload the
  agent identity before retrying.
- Lost workstation: recover the checkout plus token independently of Vault or
  OpenBao, verify coordinator host keys, and load the same wrapped SSH key.

Automatic rotation is not implemented. Replacing this shared key requires
updating all three Pis under the [rotation policy](../docs/security/rotation-and-rollback.md).

References: [OpenSSH agent operations](https://man.openbsd.org/ssh-add),
[public IdentityFile selection](https://man.openbsd.org/ssh_config#IdentityFile),
[OpenSSH serialization](https://cryptography.io/en/50.0.1/hazmat/primitives/asymmetric/serialization/).
