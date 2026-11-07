.DEFAULT_GOAL := help
SCOPE := $(abspath $(dir $(lastword $(MAKEFILE_LIST))))
PYTHON ?= python3
.PHONY: help tools check-tools render check-rendered validate
help:
	@printf '%s\n' \
	  'tools: download and verify pinned talosctl and kubectl (Linux amd64/arm64)' \
	  'check-tools: verify installed binaries offline' \
	  'render: regenerate committed public Talos YAML' \
	  'check-rendered: verify committed YAML is current' \
	  'validate: verify public bundle with pinned Talos tooling (run tools first)'
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
