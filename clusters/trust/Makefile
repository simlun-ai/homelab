.DEFAULT_GOAL := help
SCOPE := $(abspath $(dir $(lastword $(MAKEFILE_LIST))))
PYTHON ?= python3
HSM_VENV ?= $(HOME)/.local/share/homelab/venvs/hsm
.PHONY: help tools check-tools render check-rendered validate secrets-rehearse
help:
	@printf '%s\n' \
	  'tools: download and verify pinned talosctl and kubectl (Linux amd64/arm64)' \
	  'check-tools: verify installed binaries offline' \
	  'render: regenerate committed public Talos YAML' \
	  'check-rendered: verify committed YAML is current' \
	  'validate: verify public bundle with pinned Talos tooling (run tools first)' \
	  'secrets-rehearse: disposable in-memory Talos/YubiKey round trip and failure checks'
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
