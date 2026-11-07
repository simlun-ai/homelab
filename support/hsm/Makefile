.DEFAULT_GOAL := help
SCOPE := $(abspath $(dir $(lastword $(MAKEFILE_LIST))))
ROOT := $(abspath $(SCOPE)/../..)
HSM_REPO ?= $(ROOT)/tools/homelab-hsm
HSM_VENV ?= $(HOME)/.local/share/homelab/venvs/hsm
PYTHON := $(HSM_VENV)/bin/python

.PHONY: help system-dependencies tools test
help:
	@printf '%s\n' 'Application helper environment (token setup uses homelab-hsm directly):' \
	  'make -C support/hsm system-dependencies' \
	  'make -C support/hsm tools' \
	  'make -C support/hsm test'

system-dependencies:
	@bash "$(SCOPE)/install-system-dependencies.sh"

tools:
	@test -f "$(HSM_REPO)/homelab_secrets/pyproject.toml" || { printf '%s\n' 'Initialize tools/homelab-hsm or set HSM_REPO to a local checkout.' >&2; exit 2; }
	@python3 -c 'import sys; sys.exit(0 if (3, 13) <= sys.version_info[:2] < (3, 15) else "Parent helpers require Python 3.13–3.14")'
	@python3 -B "$(HSM_REPO)/homelab_secrets/scripts/offline.py" install --venv "$(HSM_VENV)"

test:
	@"$(PYTHON)" -I -B "$(ROOT)/scripts/test_helpers.py"
	@cd "$(HSM_REPO)/homelab_secrets" && "$(PYTHON)" -I -B -m unittest discover -s tests -v
