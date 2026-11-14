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
	  'render: regenerate committed public Talos YAML' \
	  'check-rendered: verify committed YAML is current' \
	  'validate: verify public bundle with pinned Talos tooling (run tools first)' \
	  'install-config-rehearse: validate a disposable full config with RAID1 and KMS patches' \
	  'secrets-rehearse: disposable in-memory Talos/YubiKey round trip and failure checks' \
	  'config-rehearse: offline disposable full config and Talos admin credential generation' \
	  'credentials-rehearse: native 24-hour client issuance on verified tmpfs (RAM_ROOT=/dev/shm)' \
	  'recovery-rehearse: disposable YubiKey recovery, configuration and 24-hour client reissuance' \
	  'admin-inspect: recover existing production authority and inspect a fresh client locally' \
	  'admin-rehearse: test administration inspection with a disposable wrapped authority' \
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
validate: check-rendered check-tools
	@"$(SCOPE)/bin/talosctl" validate --config "$(SCOPE)/talos/rendered/trust-cp1.yaml" --mode metal --strict

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
install-config-rehearse: check-tools check-rendered
	@bash -o pipefail -c '"$$1" gen config trust-install-rehearsal https://trust-install-rehearsal.invalid:6443 \
	  --install-disk /dev/REHEARSAL-DO-NOT-INSTALL \
	  --config-patch "@$$2/talos/rendered/trust-cp1.yaml" \
	  --config-patch "@$$2/talos/experiments/trust-cp1-raid1.yaml" \
	  --with-docs=false --with-examples=false --output-types controlplane --output - | \
	  "$$1" validate --mode metal --strict --config /dev/stdin' bash "$(SCOPE)/bin/talosctl" "$(SCOPE)"
