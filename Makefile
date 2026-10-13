.DEFAULT_GOAL := help
ROOT := $(abspath $(dir $(lastword $(MAKEFILE_LIST))))

.PHONY: help yubikey-help ups-help
help:
	@printf '%s\n' 'Available scopes: make yubikey-help; make ups-help'

yubikey-help:
	@$(MAKE) --no-print-directory -C "$(ROOT)/support/yubikey" help


ups-help:
	@$(MAKE) --no-print-directory -C "$(ROOT)/support/ups" help
