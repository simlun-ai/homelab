.DEFAULT_GOAL := help
ROOT := $(abspath $(dir $(lastword $(MAKEFILE_LIST))))

.PHONY: help yubikey-help
help:
	@printf '%s\n' 'Available scope: make yubikey-help'

yubikey-help:
	@$(MAKE) --no-print-directory -C "$(ROOT)/support/yubikey" help
