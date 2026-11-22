.DEFAULT_GOAL := help
SCOPE := $(abspath $(dir $(lastword $(MAKEFILE_LIST))))
PYTHON ?= python3
RAM_ROOT ?= /dev/shm
HSM_VENV ?= $(HOME)/.local/share/homelab/venvs/hsm
.PHONY: help tools check-tools render check-rendered validate secrets-rehearse config-rehearse credentials-rehearse recovery-rehearse admin-inspect admin-rehearse
help:
	@printf '%s\n' \
	  'tools: download and verify pinned talosctl and kubectl (Linux amd64/arm64)' \
	  'check-tools: verify installed binaries offline' \
	  'schematic-id SCHEMATIC=path.yaml: write the Image Factory ID to a sibling .id file' \
	  'installer-image SCHEMATIC=path.yaml: resolve and verify the pinned ARM64 installer' \
	  'render: regenerate committed public Talos YAML' \
	  'check-rendered: verify committed YAML is current' \
	  'validate: validate a disposable control-plane config with the public patches' \
	  'install-config-apply: install Talos on the assigned trust-cp1 OS mirror' \
	  'install-config-validate: recover the existing Trust identity and validate the full install config' \
	  'install-config-rehearse: validate a disposable full config with RAID1 and KMS patches' \
	  'secrets-rehearse: disposable in-memory Talos/YubiKey round trip and failure checks' \
	  'config-rehearse: offline disposable full config and Talos admin credential generation' \
	  'credentials-rehearse: native 24-hour client issuance on verified tmpfs (RAM_ROOT=/dev/shm)' \
	  'recovery-rehearse: disposable YubiKey recovery, configuration and 24-hour client reissuance' \
	  'admin-inspect: recover existing production authority and inspect a fresh client locally' \
	  'scheduling-preview / scheduling-apply: preview or apply the Trust node taint patch' \
	  'admin-rehearse: test administration inspection with a disposable wrapped authority' \
	  'zfs-key-enroll / zfs-key-verify: enroll or verify the wrapped Trust ZFS key' \
	  'zfs-key-install: deliver the enrolled key to encrypted EPHEMERAL' \
	  'tofu-tools: acquire pinned OpenTofu for the Trust infrastructure root' \
	  'tofu-key-enroll / tofu-key-verify: enroll or verify the wrapped state key' \
	  'tofu-validate / tofu-plan / tofu-apply: validate or operate Trust infrastructure' \
	  'tofu-state-recover TOFU_RECOVERY_FILE=path: recover retained infrastructure RAM state' \
	  'tofu-workload-key-enroll / tofu-workload-key-verify: enroll or verify the workload state key' \
	  'tofu-workload-validate / tofu-workload-plan / tofu-workload-apply: operate Trust workloads' \
	  'tofu-workload-state-recover TOFU_RECOVERY_FILE=path: recover retained workload RAM state' \
	  'openbao-status / openbao-initialize / openbao-unseal: operate Trust OpenBao' \
	  'openbao-restore-unseal / openbao-restore-shell: inspect a restored backup' \
	  'openbao-jobs-credentials / openbao-backup-auth / openbao-backup-init-repo: set up scheduled backups' \
	  'openbao-kms-auth KMS_CLUSTER=backup: configure Transit and Kubernetes login' \
	  'trust-kubectl KUBECTL_ARGS=...: use Trust Kubernetes credentials from memory' \
	  'kms-enroll / kms-key-verify: create or recover the wrapped trust-cp1 KMS key' \
	  'kms-window-open / kms-window-status / kms-window-lock: control the trust-cp1 KMS window'
tools:
	@$(PYTHON) -I -B "$(SCOPE)/tooling.py" install
check-tools:
	@$(PYTHON) -I -B "$(SCOPE)/tooling.py" check
render:
	@$(PYTHON) "$(SCOPE)/render.py" render
check-rendered:
	@$(PYTHON) "$(SCOPE)/render.py" check

secrets-rehearse: check-tools
	@"$(HSM_VENV)/bin/python" -I -B "$(SCOPE)/../../scripts/trust_talos_secrets.py" rehearse \
	  --talosctl "$(SCOPE)/bin/talosctl" \
	  --wrap "$(HSM_VENV)/bin/homelab-wrap" \
	  --unwrap "$(HSM_VENV)/bin/homelab-unwrap"

config-rehearse: check-tools check-rendered
	@"$(HSM_VENV)/bin/python" -I -B "$(SCOPE)/../../scripts/trust_talos_config.py" \
	  --talosctl "$(SCOPE)/bin/talosctl"

credentials-rehearse: check-tools
	@"$(HSM_VENV)/bin/python" -I -B "$(SCOPE)/../../scripts/trust_talos_credentials.py" \
	  --talosctl "$(SCOPE)/bin/talosctl" --ram-root "$(RAM_ROOT)"

recovery-rehearse: check-tools check-rendered
	@"$(HSM_VENV)/bin/python" -I -B "$(SCOPE)/../../scripts/trust_talos_recovery.py" \
	  --talosctl "$(SCOPE)/bin/talosctl" --ram-root "$(RAM_ROOT)" \
	  --wrap "$(HSM_VENV)/bin/homelab-wrap" \
	  --unwrap "$(HSM_VENV)/bin/homelab-unwrap"

admin-inspect: check-tools check-rendered
	@"$(HSM_VENV)/bin/python" -I -B "$(SCOPE)/../../scripts/trust_talos_admin.py" inspect \
	  --talosctl "$(SCOPE)/bin/talosctl" --ram-root "$(RAM_ROOT)" \
	  --unwrap "$(HSM_VENV)/bin/homelab-unwrap"

admin-rehearse: check-tools check-rendered
	@"$(HSM_VENV)/bin/python" -I -B "$(SCOPE)/../../scripts/trust_talos_admin.py" rehearse \
	  --talosctl "$(SCOPE)/bin/talosctl" --ram-root "$(RAM_ROOT)" \
	  --wrap "$(HSM_VENV)/bin/homelab-wrap" \
	  --unwrap "$(HSM_VENV)/bin/homelab-unwrap"

.PHONY: kms-enroll kms-key-verify kms-window-open kms-window-status kms-window-lock
kms-enroll: check-tools
kms-enroll: KMS_ACTION := enroll
kms-key-verify: KMS_ACTION := verify
kms-window-open: KMS_ACTION := open
kms-window-status: KMS_ACTION := status
kms-window-lock: KMS_ACTION := lock
kms-enroll kms-key-verify kms-window-open kms-window-status kms-window-lock:
	@"$(HSM_VENV)/bin/python" -I -B "$(SCOPE)/../../scripts/trust_kms_node_operator.py" \
	  $(KMS_ACTION) \
	  --talosctl "$(SCOPE)/bin/talosctl" --wrap "$(HSM_VENV)/bin/homelab-wrap" \
	  --unwrap "$(HSM_VENV)/bin/homelab-unwrap"

.PHONY: kms-probe-seal kms-probe-unseal
kms-probe-seal kms-probe-unseal:
	@"$(HSM_VENV)/bin/python" -I -B "$(SCOPE)/../../scripts/trust_kms_tls_check.py" $(patsubst kms-probe-%,%,$@)

.PHONY: install-config-rehearse
install-config-rehearse: REHEARSAL_RAID := "@$(SCOPE)/talos/experiments/trust-cp1-raid1.yaml"
validate install-config-rehearse: check-tools check-rendered
	@bash -o pipefail -c 'talosctl="$$1"; shift; "$$talosctl" gen config trust-install-rehearsal https://trust-install-rehearsal.invalid:6443 \
	  --install-disk /dev/REHEARSAL-DO-NOT-INSTALL \
	  "$$@" --with-docs=false --with-examples=false --output-types controlplane --output - | \
	  "$$talosctl" validate --mode metal --strict --config /dev/stdin' bash "$(SCOPE)/bin/talosctl" \
	  --config-patch-control-plane "@$(SCOPE)/talos/rendered/trust-cp1.yaml" \
	  $(if $(REHEARSAL_RAID),--config-patch-control-plane $(REHEARSAL_RAID))

.PHONY: install-config-validate
install-config-validate: check-tools check-rendered
	@"$(HSM_VENV)/bin/python" -I -B "$(SCOPE)/../../scripts/trust_talos_config.py" \
	  --talosctl "$(SCOPE)/bin/talosctl" --validate-install --unwrap "$(HSM_VENV)/bin/homelab-unwrap"

.PHONY: install-config-apply
install-config-apply: check-tools check-rendered
	@"$(HSM_VENV)/bin/python" -I -B "$(SCOPE)/../../scripts/trust_talos_config.py" \
	  --talosctl "$(SCOPE)/bin/talosctl" --apply-install --unwrap "$(HSM_VENV)/bin/homelab-unwrap"

export SCHEMATIC
.PHONY: schematic-id
schematic-id:
	@test -n "$$SCHEMATIC" || { echo 'Set SCHEMATIC to a public YAML file (relative to clusters/trust or absolute).' >&2; exit 2; }
	@$(PYTHON) -I -B "$(SCOPE)/schematic.py" -- "$$SCHEMATIC"

.PHONY: installer-image
installer-image: schematic-id
	@$(PYTHON) -I -B "$(SCOPE)/schematic.py" --installer-image -- "$$SCHEMATIC"

.PHONY: zfs-key-enroll zfs-key-verify
zfs-key-enroll:
	@"$(HSM_VENV)/bin/python" -I -B "$(SCOPE)/../../scripts/trust_zfs_key.py" enroll \
	  --wrap "$(HSM_VENV)/bin/homelab-wrap" --unwrap "$(HSM_VENV)/bin/homelab-unwrap"

zfs-key-verify:
	@"$(HSM_VENV)/bin/python" -I -B "$(SCOPE)/../../scripts/trust_zfs_key.py" verify \
	  --unwrap "$(HSM_VENV)/bin/homelab-unwrap"

.PHONY: zfs-key-install
zfs-key-install: check-tools
	@"$(HSM_VENV)/bin/python" -I -B "$(SCOPE)/../../scripts/trust_zfs_key_install.py" \
	  --talosctl "$(SCOPE)/bin/talosctl" --kubectl "$(SCOPE)/bin/kubectl" \
	  --unwrap "$(HSM_VENV)/bin/homelab-unwrap"

.PHONY: tofu-tools tofu-key-enroll tofu-key-verify tofu-validate tofu-plan tofu-apply tofu-check
tofu-tools:
	@$(PYTHON) -I -B "$(SCOPE)/tooling.py" install --tool tofu

tofu-check:
	@$(PYTHON) -I -B "$(SCOPE)/tooling.py" check --tool tofu

tofu-key-enroll tofu-key-verify:
	@"$(HSM_VENV)/bin/python" -I -B "$(SCOPE)/../../scripts/trust_tofu_key.py" $(patsubst tofu-key-%,%,$@)

tofu-plan tofu-apply: check-tools
tofu-validate tofu-plan tofu-apply: tofu-check
	@"$(HSM_VENV)/bin/python" -I -B "$(SCOPE)/../../scripts/trust_tofu.py" \
	  $(patsubst tofu-%,%,$@) --ram-root "$(RAM_ROOT)"

export TOFU_RECOVERY_FILE
.PHONY: tofu-state-recover
tofu-state-recover: tofu-check
	@test -n "$$TOFU_RECOVERY_FILE" || { echo 'Set TOFU_RECOVERY_FILE to the retained RAM recovery file.' >&2; exit 2; }
	@"$(HSM_VENV)/bin/python" -I -B "$(SCOPE)/../../scripts/trust_tofu.py" \
	  state-recover --ram-root "$(RAM_ROOT)" --recovery-file "$$TOFU_RECOVERY_FILE"

.PHONY: tofu-workload-key-enroll tofu-workload-key-verify
tofu-workload-key-enroll tofu-workload-key-verify:
	@"$(HSM_VENV)/bin/python" -I -B "$(SCOPE)/../../scripts/trust_tofu_key.py" \
	  $(patsubst tofu-workload-key-%,%,$@) --scope workload

.PHONY: tofu-workload-validate tofu-workload-plan tofu-workload-apply tofu-workload-state-recover
tofu-workload-plan tofu-workload-apply: check-tools
tofu-workload-validate tofu-workload-plan tofu-workload-apply: tofu-check
	@"$(HSM_VENV)/bin/python" -I -B "$(SCOPE)/../../scripts/trust_tofu.py" \
	  $(patsubst tofu-workload-%,%,$@) --scope workload --ram-root "$(RAM_ROOT)"

tofu-workload-state-recover: tofu-check
	@test -n "$$TOFU_RECOVERY_FILE" || { echo 'Set TOFU_RECOVERY_FILE to the retained RAM recovery file.' >&2; exit 2; }
	@"$(HSM_VENV)/bin/python" -I -B "$(SCOPE)/../../scripts/trust_tofu.py" \
	  state-recover --scope workload --ram-root "$(RAM_ROOT)" --recovery-file "$$TOFU_RECOVERY_FILE"

.PHONY: scheduling-preview scheduling-apply
scheduling-preview scheduling-apply: check-tools check-rendered
	@"$(HSM_VENV)/bin/python" -I -B "$(SCOPE)/../../scripts/trust_talos_admin.py" \
	  $@ --talosctl "$(SCOPE)/bin/talosctl" --ram-root "$(RAM_ROOT)" \
	  --unwrap "$(HSM_VENV)/bin/homelab-unwrap"

.PHONY: openbao-status openbao-initialize openbao-unseal
openbao-status openbao-initialize openbao-unseal: check-tools
	@"$(HSM_VENV)/bin/python" -I -B "$(SCOPE)/../../scripts/trust_openbao.py" \
	  $(patsubst openbao-%,%,$@) --ram-root "$(RAM_ROOT)"

export KUBECTL_ARGS R2_REPOSITORY KMS_CLUSTER
.PHONY: trust-kubectl openbao-restore-unseal openbao-restore-shell
.PHONY: openbao-backup-auth openbao-jobs-credentials openbao-backup-init-repo openbao-kms-auth
trust-kubectl: check-tools
	@"$(HSM_VENV)/bin/python" -I -B "$(SCOPE)/../../scripts/trust_openbao.py" kubectl --ram-root "$(RAM_ROOT)"

openbao-restore-unseal openbao-restore-shell openbao-backup-auth openbao-jobs-credentials openbao-backup-init-repo openbao-kms-auth: check-tools
	@"$(HSM_VENV)/bin/python" -I -B "$(SCOPE)/../../scripts/trust_openbao.py" \
	  $(patsubst openbao-%,%,$@) --ram-root "$(RAM_ROOT)"
