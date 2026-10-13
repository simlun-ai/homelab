.DEFAULT_GOAL := help
SCOPE := $(abspath $(dir $(lastword $(MAKEFILE_LIST))))
ROOT := $(abspath $(SCOPE)/../..)
PYTHON := $(SCOPE)/.venv/bin/python

.PHONY: help system-dependencies tools inspect program verify verify-set test
help:
	@printf '%s\n' 'Bootstrap: see docs/installation/00-yubikey-setup.md' \
	  'make -C support/yubikey system-dependencies' \
	  'make -C support/yubikey tools' \
	  'make -C support/yubikey inspect' \
	  'make -C support/yubikey program LABEL=key0' \
	  'make -C support/yubikey verify LABEL=key0' \
	  'make -C support/yubikey verify-set' \
	  'make -C support/yubikey test'

system-dependencies:
	@bash "$(SCOPE)/install-system-dependencies.sh"

tools:
	@python3 -m venv "$(SCOPE)/.venv"
	@"$(PYTHON)" -m pip install -r "$(SCOPE)/requirements.txt"
	@"$(PYTHON)" -m pip check

inspect verify-set:
	@"$(PYTHON)" -I -B "$(ROOT)/scripts/yubikey_cli.py" $@

program verify:
	@case "$(LABEL)" in key0|key1|key2|key3) ;; *) printf '%s\n' 'Set LABEL=key0, key1, key2, or key3.' >&2; exit 2;; esac
	@"$(PYTHON)" -I -B "$(ROOT)/scripts/yubikey_cli.py" $@ --label "$(LABEL)"

test:
	@"$(PYTHON)" -I -B "$(ROOT)/scripts/test_helpers.py"
