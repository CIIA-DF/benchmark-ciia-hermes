UV ?= uv
.PHONY: setup up down demo demo-compose check test-backend test-documents test-integration serve
setup:
	$(UV) sync --locked
up down demo demo-compose check test-backend test-documents test-integration serve:
	$(UV) run --locked python -m scripts.dev $@
