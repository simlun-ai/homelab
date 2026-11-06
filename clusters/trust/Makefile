.DEFAULT_GOAL := help
SCOPE := $(abspath $(dir $(lastword $(MAKEFILE_LIST))))
PYTHON ?= python3
.PHONY: help render check-rendered
help:
	@printf '%s\n' 'render: regenerate committed public Talos YAML' 'check-rendered: verify committed YAML is current'
render:
	@$(PYTHON) "$(SCOPE)/render.py" render
check-rendered:
	@$(PYTHON) "$(SCOPE)/render.py" check
