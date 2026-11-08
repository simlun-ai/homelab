.DEFAULT_GOAL := help
SCOPE := $(abspath $(dir $(lastword $(MAKEFILE_LIST))))
PYTHON ?= python3
RAM_ROOT ?= /dev/shm
HSM_VENV ?= $(HOME)/.local/share/homelab/venvs/hsm
.PHONY: help tools check-tools render check-rendered validate secrets-rehearse config-rehearse credentials-rehearse recovery-rehearse
help:
	@printf '%s\n' \
	  'tools: download and verify pinned talosctl and kubectl (Linux amd64/arm64)' \
	  'check-tools: verify installed binaries offline' \
	  'render: regenerate committed public Talos YAML' \
	  'check-rendered: verify committed YAML is current' \
	  'validate: verify public bundle with pinned Talos tooling (run tools first)' \
	  'secrets-rehearse: disposable in-memory Talos/YubiKey round trip and failure checks' \
	  'config-rehearse: offline disposable full config and Talos admin credential generation' \
	  'credentials-rehearse: native 24-hour client issuance on verified tmpfs (RAM_ROOT=/dev/shm)' \
	  'recovery-rehearse: disposable YubiKey recovery, configuration and 24-hour client reissuance'
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
