# Developer entry points. Everything here is also what CI runs.

VENV ?= venv
PY   ?= $(VENV)/bin/python
PIP  ?= $(VENV)/bin/pip

.PHONY: help venv install test test-js lint format audit coverage run check clean

help:
	@echo "make install   - create the venv and install dev dependencies"
	@echo "make test      - run the Python test suite"
	@echo "make test-js   - run the Node assertions for static/js/app.js"
	@echo "make lint      - ruff check + ruff format --check"
	@echo "make format    - ruff format (rewrites files)"
	@echo "make audit     - pip-audit against the runtime requirements"
	@echo "make coverage  - test suite with a coverage report"
	@echo "make run       - start the development server on :5000"
	@echo "make check     - lint + test + test-js + audit (what CI runs)"

venv:
	test -d $(VENV) || python3 -m venv $(VENV)

install: venv
	$(PIP) install --upgrade pip
	$(PIP) install -r requirements-dev.txt

test:
	$(PY) -m pytest tests/ -v

test-js:
	node tests/js/test_export_sanitize.mjs
	node tests/js/test_render_caps.mjs
	node tests/js/test_features.mjs

lint:
	$(VENV)/bin/ruff check .
	$(VENV)/bin/ruff format --check .

format:
	$(VENV)/bin/ruff format .
	$(VENV)/bin/ruff check . --fix

audit:
	$(VENV)/bin/pip-audit -r requirements.txt

coverage:
	$(VENV)/bin/coverage run -m pytest tests/
	$(VENV)/bin/coverage report -m

run:
	$(PY) app.py

check: lint test test-js audit

clean:
	find . -type d -name __pycache__ -prune -exec rm -rf {} +
	rm -rf .pytest_cache .coverage .ruff_cache
