.DEFAULT_GOAL := help
ROOT := $(abspath $(dir $(lastword $(MAKEFILE_LIST))))

.PHONY: help yubikey-help ups-help ci
help:
	@printf '%s\n' 'Available scopes: make yubikey-help; make ups-help' 'Checks: make ci'

yubikey-help:
	@$(MAKE) --no-print-directory -C "$(ROOT)/support/yubikey" help


ups-help:
	@$(MAKE) --no-print-directory -C "$(ROOT)/support/ups" help

ci:
	@test -f "$(ROOT)/tools/homelab-hsm/homelab_secrets/pyproject.toml" || { printf '%s\n' 'Initialize public code: git submodule update --init --recursive -- tools/homelab-hsm' >&2; exit 2; }
	cd "$(ROOT)" && docker buildx bake --file docker-bake.hcl --progress=plain ci
