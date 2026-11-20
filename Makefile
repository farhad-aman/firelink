VENV  := $(HOME)/.local/share/firelink/venv
PY    := $(VENV)/bin/python
SHIM  := $(HOME)/.local/bin/firelink

LEGACY_VENV := $(HOME)/.local/share/dl
LEGACY_SHIM := $(HOME)/.local/bin/dl

.PHONY: install test uninstall

install: $(PY)
	$(PY) -m pip install -q -e .
	@mkdir -p $(dir $(SHIM))
	@printf '#!/bin/sh\nexec %s -m firelink "$$@"\n' "$(PY)" > $(SHIM)
	@chmod 755 $(SHIM)
	@if grep -qs '$(LEGACY_VENV)/venv' $(LEGACY_SHIM); then rm -rf $(LEGACY_SHIM) $(LEGACY_VENV); echo "removed old dl: $(LEGACY_SHIM)"; fi
	@echo "installed: $(SHIM)"

$(PY):
	python3 -m venv $(VENV)
	$(VENV)/bin/pip install -q --upgrade pip

test: $(PY)
	$(PY) -m pip install -q -e ".[dev]"
	$(PY) -m pytest

uninstall:
	rm -rf $(VENV) $(SHIM)
