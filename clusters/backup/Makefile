.DEFAULT_GOAL := help
SCOPE := $(abspath $(dir $(lastword $(MAKEFILE_LIST))))
PYTHON ?= python3
HSM_VENV ?= $(HOME)/.local/share/homelab/venvs/hsm
RAM_ROOT ?= /dev/shm
TOOLING := "$(SCOPE)/../trust/tooling.py"
TALOSCTL := "$(SCOPE)/bin/talosctl"
INSTALLER_PIN := "$(SCOPE)/talos/backup-cp1.schematic.amd64.image"
TALOS_VERSION := $(shell awk '/^talos:$$/ {getline; print $$2}' "$(SCOPE)/versions.yaml")
KUBERNETES_VERSION := $(shell awk '/^kubernetes:$$/ {getline; print $$2}' "$(SCOPE)/versions.yaml")

.PHONY: help tools check-tools validate schematic-id installer-image
.PHONY: secrets-init install-config-validate install-config-apply install-status
help:
	@printf '%s\n' 'tools / check-tools: install or verify the pinned Backup talosctl' \
	  'validate: validate the public Backup install patch offline with disposable credentials' \
	  'schematic-id SCHEMATIC=path: submit a public schematic and write its ID' \
	  'installer-image SCHEMATIC=path: regenerate the ID and digest-only amd64 installer pin' \
	  'secrets-init: generate and wrap the Backup Talos identity once' \
	  'install-config-validate / install-config-apply: validate or install using the wrapped identity' \
	  'install-status: verify the encrypted system volumes with an in-memory Talos client'
tools:
	@$(PYTHON) -I -B $(TOOLING) install --tool talosctl --scope "$(SCOPE)"
check-tools:
	@$(PYTHON) -I -B $(TOOLING) check --tool talosctl --scope "$(SCOPE)"
validate: check-tools
	@bash -e -o pipefail -c 'image=$$(cat "$$4"); test -n "$$image"; \
	  "$$1" gen config backup https://10.10.0.15:6443 \
	  --talos-version "$$2" --kubernetes-version "$$3" \
	  --install-disk /dev/REHEARSAL-DO-NOT-INSTALL \
	  --install-image "$$image" --config-patch-control-plane "@$$5" \
	  --with-docs=false --with-examples=false --output-types controlplane --output - | \
	  "$$1" validate --mode metal --strict --config /dev/stdin' \
	  bash $(TALOSCTL) "$(TALOS_VERSION)" "$(KUBERNETES_VERSION)" $(INSTALLER_PIN) "$(SCOPE)/talos/backup-cp1.yaml"

export SCHEMATIC
schematic-id:
	@test -n "$$SCHEMATIC" || { echo 'Set SCHEMATIC to a public YAML file (relative to clusters/backup or absolute).' >&2; exit 2; }
	@$(PYTHON) -I -B "$(SCOPE)/../trust/schematic.py" -- "$$SCHEMATIC"

installer-image: schematic-id
	@$(PYTHON) -I -B "$(SCOPE)/../trust/schematic.py" --installer-image \
	  --arch amd64 --scope "$(SCOPE)" -- "$$SCHEMATIC"

secrets-init: INSTALL_ACTION := enroll
secrets-init: HSM_TOOL := homelab-wrap
install-config-validate: INSTALL_ACTION := validate
install-config-apply: INSTALL_ACTION := apply
install-status: INSTALL_ACTION := status
install-config-validate install-config-apply install-status: HSM_TOOL := homelab-unwrap
secrets-init install-config-validate install-config-apply install-status: check-tools
	@"$(HSM_VENV)/bin/python" -I -B "$(SCOPE)/../../scripts/backup_talos_install.py" \
	  $(INSTALL_ACTION) --talosctl $(TALOSCTL) --hsm-tool "$(HSM_VENV)/bin/$(HSM_TOOL)" \
	  --ram-root "$(RAM_ROOT)"
