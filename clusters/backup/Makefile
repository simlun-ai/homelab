.DEFAULT_GOAL := help
SCOPE := $(abspath $(dir $(lastword $(MAKEFILE_LIST))))
PYTHON ?= python3
TOOLING := "$(SCOPE)/../trust/tooling.py"
TALOSCTL := "$(SCOPE)/bin/talosctl"
TALOS_VERSION := $(shell awk '/^talos:$$/ {getline; print $$2}' "$(SCOPE)/versions.yaml")
KUBERNETES_VERSION := $(shell awk '/^kubernetes:$$/ {getline; print $$2}' "$(SCOPE)/versions.yaml")

.PHONY: help tools check-tools validate schematic-id
help:
	@printf '%s\n' 'tools / check-tools: install or verify the pinned Backup talosctl' \
	  'validate: validate the public Backup install patch offline with disposable credentials' \
	  'schematic-id SCHEMATIC=path: submit a public schematic and write its ID'
tools:
	@$(PYTHON) -I -B $(TOOLING) install --tool talosctl --scope "$(SCOPE)"
check-tools:
	@$(PYTHON) -I -B $(TOOLING) check --tool talosctl --scope "$(SCOPE)"
validate: check-tools
	@bash -o pipefail -c '"$$1" gen config backup https://10.10.0.15:6443 \
	  --talos-version "$$2" --kubernetes-version "$$3" \
	  --install-disk /dev/REHEARSAL-DO-NOT-INSTALL \
	  --config-patch-control-plane "@$$4" \
	  --with-docs=false --with-examples=false --output-types controlplane --output - | \
	  "$$1" validate --mode metal --strict --config /dev/stdin' \
	  bash $(TALOSCTL) "$(TALOS_VERSION)" "$(KUBERNETES_VERSION)" "$(SCOPE)/talos/backup-cp1.yaml"

export SCHEMATIC
schematic-id:
	@test -n "$$SCHEMATIC" || { echo 'Set SCHEMATIC to a public YAML file (relative to clusters/backup or absolute).' >&2; exit 2; }
	@$(PYTHON) -I -B "$(SCOPE)/../trust/schematic.py" -- "$$SCHEMATIC"
