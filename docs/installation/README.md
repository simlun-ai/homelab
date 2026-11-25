# Installation

Main TODO list for installing the homelab and implementing its helpers and repository layout. Work through one step at a time, expanding the runbook and code as each installation is tried for real.

## Main TODO list

| Step | Runbook | Implementation | Real-install verification |
| --- | --- | --- | --- |
| [00 - YubiKey setup](00-yubikey-setup.md) | Verified procedure | Offline setup helpers, shared wrapping library/CLI and external virtualenv | PASS 2026-11-04: all four tokens, cross-token/software unwrap and independent replica retrieval |
| [01 - Main coordinator](01-main-coordinator.md) | Shared base setup linked; additional KMS TODO | Base inventory, scoped tools, bootstrap/hardening/verification, wrapped administrator password and shared SSH key workflows; KMS TODO | `ups-aux` base setup verified on 2026-11-06. Locked production TLS verified on 2026-11-11; live-node authorization pending. |
| [02 - Trust](02-trust.md) | Living encrypted Talos/Kubernetes bootstrap roadmap and draft Pi 4 UEFI experiment | Encrypted Talos, Kubernetes, ZFS LocalPV, [cert-manager](trust-cert-manager.md), and [MetalLB](trust-metallb.md) installed. [OpenBao workload](trust-openbao.md) initialized and unsealed. The [HTTPS listener](trust-openbao-network.md) is active. | Encrypted boot, Kubernetes, retained LocalPV, and staging DNS-01 issuance verified. OpenBao local DNS and HTTPS verified from the operator workstation. Pi and Metal client checks are deferred. Encrypted state published for both roots. |

Keep detailed TODOs and verification results in the owning runbook. Update this table as work progresses; written instructions or configuration alone do not establish a verified installation.

Later milestones; split and number their runbooks when the next step is concrete:

- [ ] [Boot the first Backup Talos node](03-backup.md) through the Trust-hosted KMS adapter, then return to finishing Trust.
- [ ] Set up Trust's [certificate factory](../clusters.md#certificate-factory) with External Secrets Operator and OpenBao after OpenBao is deployed.
- [ ] Install Backup and its services. Verify Garage serves the certificate delivered by the factory and picks up a renewal.
- [ ] Install Pi, its coordinator, and home automation workloads.
- [ ] Deploy [central monitoring on Pi](../clusters.md#central-monitoring), then install lightweight collectors on Trust and Backup and verify that Pi receives metrics from both.
- [ ] Install Metal, its coordinator, and heavier workloads.
- [ ] Deploy Headlamp on Backup, Pi, and Metal as each cluster comes online.

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
| `support/hsm/` | Offline environment for parent application helpers; standalone step 00 uses the homelab-hsm Python CLI. |
| `support/ups/` | Coordinator configuration, Ansible, services, and scoped tooling. |
| `secrets/manifest.json` | Public credential catalogue. |
| `secrets/wrapped/` | Private `homelab-secrets` submodule containing authenticated encrypted records only. |
| `tools/homelab-hsm/` | Separate code submodule containing the shared `homelab_secrets/` Python project, CLI, dependencies, and tests. |
| `clusters/trust/`, `make/` | Trust configuration, version pins, and shared Make implementation. |

Installation runbooks own executable procedures, with shared coordinator OS/Ansible setup in [the reusable base runbook](../../runbooks/ups-coordinator-base-setup.md). Keep architecture, security policy, and backup design in their [existing owning documents](../layout.md#document-ownership), linking to them here. Keep related documentation synchronized as decisions and verified behavior change.
