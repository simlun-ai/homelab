# Installation

Main TODO list for installing the homelab and implementing its helpers and repository layout. Work through one step at a time, expanding the runbook and code as each installation is tried for real.

## Main TODO list

| Step | Runbook | Implementation | Real-install verification |
| --- | --- | --- | --- |
| [00 - YubiKey setup](00-yubikey-setup.md) | First runbook | Setup/wrapping helpers, system installer, and virtualenv | Not tried on hardware |
| [01 - Main coordinator](01-main-coordinator.md) | Placeholder | TODO | Not tried |
| [02 - Vault](02-vault.md) | Placeholder | TODO | Not tried |

Keep detailed TODOs and verification results in the owning runbook. Update this table as work progresses; written instructions or configuration alone do not establish a verified installation.

Later milestones; split and number their runbooks when the next step is concrete:

- [ ] Prepare Vault's OpenBao-backed KMS service for dependent clusters.
- [ ] Install Backup and its services.
- [ ] Install Pi, its coordinator, and home automation workloads.
- [ ] Install Metal, its coordinators, and heavier workloads.

## Working method

1. Settle the next step's blocking TBDs and write its prerequisites, ordered commands, expected results, and recovery actions. Identify the host where each command runs.
2. Implement the required helpers, configuration, pinned tooling, and Make entry points alongside the instructions.
3. Try the step on the actual hardware and correct the code and runbook from the results.
4. Record the tested repository revision, relevant tools/hardware, outcome, and remaining problems without secret output. Mark verification complete only after the required checks pass.
5. Continue with the next sensible step, adding `NN-<headline>.md` runbooks as needed.

## Incremental repository layout

Create each part when a runbook first needs it, following [layout.md](../layout.md):

| Path | First use |
| --- | --- |
| `scripts/homelab/`, `pyproject.toml` | Python helpers, including any token programming/verification support needed in step 00. |
| `support/yubikey/` | Step 00 system dependencies, Python requirements, and explicit Make entry points. |
| `support/ups/` | Coordinator configuration, Ansible, services, and scoped tooling. |
| `secrets/wrapped/` | Authenticated encrypted records and their public manifest. |
| `clusters/vault/`, `make/` | Vault configuration, version pins, and shared Make implementation. |

Installation runbooks own executable procedures. Keep architecture, security policy, and backup design in their [existing owning documents](../layout.md#document-ownership), linking to them here. Keep related documentation synchronized as decisions and verified behavior change.
