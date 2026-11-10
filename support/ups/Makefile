.DEFAULT_GOAL := help
SCOPE := $(abspath $(dir $(lastword $(MAKEFILE_LIST))))
HSM_VENV ?= $(HOME)/.local/share/homelab/venvs/hsm
PYTHON := $(SCOPE)/.venv/bin/python
ANSIBLE_PLAYBOOK := $(SCOPE)/.venv/bin/ansible-playbook
export ANSIBLE_CONFIG := $(SCOPE)/ansible.cfg
export ANSIBLE_LOCAL_TEMP := $(SCOPE)/.ansible/tmp
export HOST
export ASK_BECOME_PASS
export ACME_EMAIL
DNS_RECORD ?= $(abspath $(SCOPE)/../../secrets/wrapped/ups-aux-cloudflare-dns-api.json)
export DNS_RECORD

.PHONY: help system-dependencies tools check-tools inventory syntax bootstrap verify harden verify-hardening diff apply
help:
	@printf '%s\n' \
	  'Setup: runbooks/ups-coordinator-base-setup.md' \
	  'make -C support/ups system-dependencies' \
	  'make -C support/ups tools' \
	  'make -C support/ups inventory' \
	  'make -C support/ups syntax' \
	  'make -C support/ups ssh-key-create (once, with YubiKey)' \
	  'make -C support/ups ssh-key-load (before remote operations)' \
	  'make -C support/ups ssh-key-unload' \
	  'make -C support/ups bootstrap HOST=ups-aux' \
	  'make -C support/ups verify HOST=ups-aux' \
	  'make -C support/ups harden HOST=ups-aux' \
	  'make -C support/ups verify-hardening HOST=ups-aux' \
  'make -C support/ups diff HOST=ups-aux (preview bootstrap and hardening)' \
  'make -C support/ups apply HOST=ups-aux (apply bootstrap and hardening with diffs)' \
	  'Password workflow: runbooks/coordinator-passwords.md (password-create/reveal/apply)' \
	  'HOST must be exactly ups-aux, ups-pi, or ups-metal.' \
	  'make -C support/ups kms-stage HOST=ups-aux (install and verify locked local service)' \
	  'make -C support/ups kms-acme-tools HOST=ups-aux' \
	  'make -C support/ups kms-acme-rehearse HOST=ups-aux ACME_EMAIL=...' \
	  'make -C support/ups kms-acme-state HOST=ups-aux ACME_EMAIL=... [ACME_STATE_MODE=init|recover|recreate]' \
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
	@"$(ANSIBLE_PLAYBOOK)" -i "$(SCOPE)/inventory.yaml" --syntax-check "$(SCOPE)/ansible/playbooks/harden.yaml"
	@"$(ANSIBLE_PLAYBOOK)" -i "$(SCOPE)/inventory.yaml" --syntax-check "$(SCOPE)/ansible/playbooks/verify-hardening.yaml"
	@"$(ANSIBLE_PLAYBOOK)" -i "$(SCOPE)/inventory.yaml" --syntax-check "$(SCOPE)/ansible/playbooks/kms-stage.yaml"
	@"$(ANSIBLE_PLAYBOOK)" -i "$(SCOPE)/inventory.yaml" --syntax-check "$(SCOPE)/ansible/playbooks/kms-acme-tools.yaml"

bootstrap verify harden verify-hardening diff apply: check-tools ssh-key-check
	@case "$$HOST" in ups-aux|ups-pi|ups-metal) ;; \
	  *) printf '%s\n' 'Set HOST to exactly ups-aux, ups-pi, or ups-metal.' >&2; exit 2;; esac; \
	case "$$ASK_BECOME_PASS" in ''|0) set -- ;; \
	  1) test "$@" = bootstrap || { printf '%s\n' 'ASK_BECOME_PASS is only for bootstrap.' >&2; exit 2; }; set -- --ask-become-pass ;; \
	  *) printf '%s\n' 'ASK_BECOME_PASS must be 0 or 1.' >&2; exit 2;; esac; \
	case "$@" in \
	  diff|apply) \
	    set -- "$$@" --diff "$(SCOPE)/ansible/playbooks/bootstrap.yaml" "$(SCOPE)/ansible/playbooks/harden.yaml"; \
	    if [ "$@" = diff ]; then set -- --check "$$@"; fi ;; \
	  *) set -- "$$@" "$(SCOPE)/ansible/playbooks/$@.yaml" ;; \
	esac; \
	exec "$(ANSIBLE_PLAYBOOK)" -i "$(SCOPE)/inventory.yaml" --limit "$$HOST" "$$@"

# Reuse the pinned token SDK environment; no secret values enter Make or Ansible.
.PHONY: password-create password-reveal password-apply
password-create password-reveal password-apply:
	@case "$$HOST" in ups-aux|ups-pi|ups-metal) ;; \
	  *) printf '%s\n' 'Set HOST to exactly ups-aux, ups-pi, or ups-metal.' >&2; exit 2;; esac; \
	exec "$(HSM_VENV)/bin/python" -I -B \
	  "$(SCOPE)/../../scripts/coordinator_password_cli.py" $(patsubst password-%,%,$@) --host "$$HOST"

.PHONY: ssh-key-create ssh-key-load ssh-key-public ssh-key-unload ssh-key-check
ssh-key-create ssh-key-load ssh-key-public:
	@"$(HSM_VENV)/bin/python" -I -B \
	  "$(SCOPE)/../../scripts/coordinator_ssh_cli.py" $(patsubst ssh-key-%,%,$@)

ssh-key-check ssh-key-unload: check-tools
	@"$(PYTHON)" -I -B "$(SCOPE)/../../scripts/coordinator_ssh_cli.py" $(patsubst ssh-key-%,%,$@)

password-apply: ssh-key-check

.PHONY: kms-stage
kms-stage: check-tools ssh-key-check
	@test "$$HOST" = ups-aux || { printf '%s\n' 'Set HOST to ups-aux for Trust KMS staging.' >&2; exit 2; }
	@"$(ANSIBLE_PLAYBOOK)" -i "$(SCOPE)/inventory.yaml" --limit ups-aux --diff "$(SCOPE)/ansible/playbooks/kms-stage.yaml"

.PHONY: kms-acme-tools kms-acme-rehearse
kms-acme-tools: check-tools ssh-key-check
	@test "$$HOST" = ups-aux || { printf '%s\n' 'Set HOST to ups-aux for Trust ACME.' >&2; exit 2; }
	@"$(ANSIBLE_PLAYBOOK)" -i "$(SCOPE)/inventory.yaml" --limit ups-aux --diff "$(SCOPE)/ansible/playbooks/kms-acme-tools.yaml"

kms-acme-rehearse: ssh-key-check
	@test "$$HOST" = ups-aux || { printf '%s\n' 'Set HOST to ups-aux for Trust ACME.' >&2; exit 2; }
	@"$(HSM_VENV)/bin/python" -I -B "$(SCOPE)/../../scripts/trust_kms_acme_operator.py" \
	  --email "$$ACME_EMAIL" --record "$$DNS_RECORD" --unwrap "$(HSM_VENV)/bin/homelab-unwrap"

# This command only issues staging certificates. Recovery is the default.
ACME_STATE_MODE ?= recover
.PHONY: kms-acme-state
kms-acme-state: ssh-key-check
	@test "$$HOST" = ups-aux || { printf '%s\n' 'Set HOST to ups-aux for Trust ACME.' >&2; exit 2; }
	@"$(HSM_VENV)/bin/python" -I -B "$(SCOPE)/../../scripts/trust_kms_acme_state_operator.py" \
	  --mode "$(ACME_STATE_MODE)" --email "$$ACME_EMAIL" \
	  --wrap "$(HSM_VENV)/bin/homelab-wrap" --unwrap "$(HSM_VENV)/bin/homelab-unwrap"
