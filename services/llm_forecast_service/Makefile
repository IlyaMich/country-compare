PYTHON ?= python
PORT ?= 8080

PACKAGE_DIR := src/llm_forecast_service
TEST_DIR := tests

.PHONY: help install install-dev test lint lint-fix format format-check typecheck check run run-dev clean

help:
	@echo "LLM Forecast Service targets:"
	@echo "  make install        Install service runtime dependencies"
	@echo "  make install-dev    Install service with dev dependencies"
	@echo "  make test           Run service tests"
	@echo "  make lint           Run ruff"
	@echo "  make lint-fix       Run ruff with --fix"
	@echo "  make format         Run black"
	@echo "  make format-check   Check black formatting"
	@echo "  make typecheck      Run mypy"
	@echo "  make check          Run lint, format-check, typecheck, and tests"
	@echo "  make run            Run service using current environment"
	@echo "  make run-dev        Run service with local dummy development env"
	@echo "  make clean          Remove local caches"

install:
	$(PYTHON) -m pip install .

install-dev:
	$(PYTHON) -m pip install -e ".[dev]"

test:
	$(PYTHON) -m pytest

lint:
	$(PYTHON) -m ruff check $(PACKAGE_DIR) $(TEST_DIR)

lint-fix:
	$(PYTHON) -m ruff check --fix $(PACKAGE_DIR) $(TEST_DIR)

format:
	$(PYTHON) -m black $(PACKAGE_DIR) $(TEST_DIR)

format-check:
	$(PYTHON) -m black --check $(PACKAGE_DIR) $(TEST_DIR)

typecheck:
	$(PYTHON) -m mypy $(PACKAGE_DIR)

check: lint format-check typecheck test

check-strict: check

run:
	$(PYTHON) -m uvicorn llm_forecast_service.main:app --host 0.0.0.0 --port $(PORT)

run-dev:
	LLM_SERVICE_TOKEN=dev-token \
	MISTRAL_API_KEY=dummy \
	MISTRAL_MODEL=mistral-large-latest \
	LLM_PROVIDER=mistral \
	$(PYTHON) -m uvicorn llm_forecast_service.main:app --host 0.0.0.0 --port $(PORT)

clean:
	$(PYTHON) -c "import shutil, pathlib; [shutil.rmtree(p, ignore_errors=True) for p in pathlib.Path('.').rglob('__pycache__')]"
	$(PYTHON) -c "import shutil; [shutil.rmtree(p, ignore_errors=True) for p in ['.pytest_cache', '.mypy_cache', '.ruff_cache', 'src/*.egg-info']]"