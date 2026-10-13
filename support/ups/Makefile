.DEFAULT_GOAL := help
SCOPE := $(abspath $(dir $(lastword $(MAKEFILE_LIST))))
PYTHON := $(SCOPE)/.venv/bin/python
ANSIBLE_PLAYBOOK := $(SCOPE)/.venv/bin/ansible-playbook
export ANSIBLE_CONFIG := $(SCOPE)/ansible.cfg
export ANSIBLE_LOCAL_TEMP := $(SCOPE)/.ansible/tmp
export HOST
export ASK_BECOME_PASS

.PHONY: help system-dependencies tools check-tools inventory syntax bootstrap verify
help:
	@printf '%s\n' \
	  'Setup: runbooks/ups-coordinator-base-setup.md' \
	  'make -C support/ups system-dependencies' \
	  'make -C support/ups tools' \
	  'make -C support/ups inventory' \
	  'make -C support/ups syntax' \
	  'make -C support/ups bootstrap HOST=ups-aux' \
	  'make -C support/ups verify HOST=ups-aux' \
	  'HOST must be exactly ups-aux, ups-pi, or ups-metal.' \
	  'For initial sudo setup only: bootstrap HOST=... ASK_BECOME_PASS=1'

system-dependencies:
	@bash "$(SCOPE)/install-system-dependencies.sh"

tools:
	@python3 "$(SCOPE)/check-tools.py" --python-only
	@python3 -m venv "$(SCOPE)/.venv"
	@"$(PYTHON)" -m pip install --disable-pip-version-check -r "$(SCOPE)/requirements.txt"
	@"$(PYTHON)" -m pip check
	@"$(PYTHON)" "$(SCOPE)/check-tools.py"

check-tools:
	@test -x "$(PYTHON)" || { printf '%s\n' 'Run make -C support/ups tools first.' >&2; exit 2; }
	@"$(PYTHON)" "$(SCOPE)/check-tools.py"

inventory: check-tools
	@"$(SCOPE)/.venv/bin/ansible-inventory" -i "$(SCOPE)/inventory.yaml" --graph

syntax: check-tools
	@"$(ANSIBLE_PLAYBOOK)" -i "$(SCOPE)/inventory.yaml" --syntax-check "$(SCOPE)/ansible/playbooks/bootstrap.yaml"
	@"$(ANSIBLE_PLAYBOOK)" -i "$(SCOPE)/inventory.yaml" --syntax-check "$(SCOPE)/ansible/playbooks/verify.yaml"

bootstrap verify: check-tools
	@case "$$HOST" in ups-aux|ups-pi|ups-metal) ;; \
	  *) printf '%s\n' 'Set HOST to exactly ups-aux, ups-pi, or ups-metal.' >&2; exit 2;; esac; \
	case "$$ASK_BECOME_PASS" in ''|0) set -- ;; \
	  1) test "$@" = bootstrap || { printf '%s\n' 'ASK_BECOME_PASS is only for bootstrap.' >&2; exit 2; }; set -- --ask-become-pass ;; \
	  *) printf '%s\n' 'ASK_BECOME_PASS must be 0 or 1.' >&2; exit 2;; esac; \
	exec "$(ANSIBLE_PLAYBOOK)" -i "$(SCOPE)/inventory.yaml" \
	  --limit "$$HOST" "$$@" "$(SCOPE)/ansible/playbooks/$@.yaml"
