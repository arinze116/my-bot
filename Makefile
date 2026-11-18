.PHONY: setup lint test ci run-once smoke-sources offsite-backup brand-avatar

PYTHON := .venv/bin/python
PIP := .venv/bin/pip

.venv/bin/pytest: requirements.txt requirements-dev.txt
	python3 -m venv .venv
	$(PIP) install --upgrade pip
	$(PIP) install -r requirements-dev.txt

setup: .venv/bin/pytest

lint: setup
	.venv/bin/ruff check .

test: setup
	$(PYTHON) -m pytest

ci: lint test

run-once: setup
	$(PYTHON) main.py --run-once

smoke-sources: setup
	$(PYTHON) -m scripts.check_sources

offsite-backup: setup
	$(PYTHON) -m scripts.offsite_backup

brand-avatar: setup
	$(PYTHON) -m scripts.render_brand_avatar
