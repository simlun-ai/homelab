.DEFAULT_GOAL := help
SCOPE := $(abspath $(dir $(lastword $(MAKEFILE_LIST))))
ROOT := $(abspath $(SCOPE)/../..)
PYTHON := $(SCOPE)/.venv/bin/python

.PHONY: help system-dependencies tools inspect program replace verify verify-set test
help:
	@printf '%s\n' 'Bootstrap: see docs/installation/00-yubikey-setup.md' \
	  'make -C support/yubikey system-dependencies' \
	  'make -C support/yubikey tools' \
	  'make -C support/yubikey inspect' \
	  'make -C support/yubikey program LABEL=key0' \
	  'make -C support/yubikey replace LABEL=key0' \
	  'make -C support/yubikey verify LABEL=key0' \
	  'make -C support/yubikey verify-set' \
	  'make -C support/yubikey test'

system-dependencies:
	@bash "$(SCOPE)/install-system-dependencies.sh"

tools:
	@test -f "$(ROOT)/tools/homelab-hsm/homelab_secrets/pyproject.toml" || { printf '%s\n' 'Initialize tools/homelab-hsm: git submodule update --init --recursive -- tools/homelab-hsm' >&2; exit 2; }
	@python3 -m venv "$(SCOPE)/.venv"
	@"$(PYTHON)" -m pip install -r "$(SCOPE)/requirements.txt"
	@"$(PYTHON)" -m pip install --no-build-isolation --editable "$(ROOT)/tools/homelab-hsm/homelab_secrets"
	@"$(PYTHON)" -m pip check

inspect verify-set:
	@"$(PYTHON)" -I -B "$(ROOT)/scripts/yubikey_cli.py" $@

program replace verify:
	@case "$(LABEL)" in key0|key1|key2|key3) ;; *) printf '%s\n' 'Set LABEL=key0, key1, key2, or key3.' >&2; exit 2;; esac
	@"$(PYTHON)" -I -B "$(ROOT)/scripts/yubikey_cli.py" $(if $(filter replace,$@),program --replace,$@) --label "$(LABEL)"

test:
	@"$(PYTHON)" -I -B "$(ROOT)/scripts/test_helpers.py"
	@cd "$(ROOT)/tools/homelab-hsm/homelab_secrets" && "$(PYTHON)" -I -B -m unittest discover -s tests -v
