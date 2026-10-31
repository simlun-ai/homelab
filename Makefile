.DEFAULT_GOAL := help
ROOT := $(abspath $(dir $(lastword $(MAKEFILE_LIST))))

.PHONY: help yubikey-help ups-help ci lint format typecheck ansible-lint
help:
	@printf '%s\n' 'Available scopes: make yubikey-help; make ups-help' 'Checks: make ci; make lint; make format; make typecheck; make ansible-lint'

yubikey-help:
	@$(MAKE) --no-print-directory -C "$(ROOT)/support/hsm" help


ups-help:
	@$(MAKE) --no-print-directory -C "$(ROOT)/support/ups" help

ci:
	@test -f "$(ROOT)/tools/homelab-hsm/homelab_secrets/pyproject.toml" || { printf '%s\n' 'Initialize public code: git submodule update --init --recursive -- tools/homelab-hsm' >&2; exit 2; }
	cd "$(ROOT)" && docker buildx bake --file docker-bake.hcl --progress=plain ci

lint:
	cd "$(ROOT)" && docker buildx bake --file docker-bake.hcl --progress=plain lint

format:
	cd "$(ROOT)" && docker buildx bake --file docker-bake.hcl --progress=plain lint-tool
	docker run --rm --network none --user "$$(id -u):$$(id -g)" \
	  --mount "type=bind,src=$(ROOT),dst=/project" \
	  homelab-ruff:local sh -c \
	  'ruff check --fix --no-cache scripts tests support ci && ruff format --no-cache scripts tests support ci'

typecheck:
	@test -f "$(ROOT)/tools/homelab-hsm/homelab_secrets/pyproject.toml" || { printf '%s\n' 'Initialize public code: git submodule update --init --recursive -- tools/homelab-hsm' >&2; exit 2; }
	cd "$(ROOT)" && docker buildx bake --file docker-bake.hcl --progress=plain typecheck

ansible-lint:
	cd "$(ROOT)" && docker buildx bake --file docker-bake.hcl --progress=plain ansible-lint
