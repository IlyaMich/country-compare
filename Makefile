PYTHON ?= python

APP_PACKAGE_DIR := src/country_compare
APP_TEST_DIR := tests
SCRIPT_DIR := scripts
LLM_SERVICE_DIR := services/llm_forecast_service

.PHONY: help install install-dev format format-check lint lint-fix typecheck test check check-strict clean
.PHONY: llm-install llm-install-dev llm-test llm-lint llm-format llm-format-check llm-typecheck llm-check llm-run llm-run-dev
.PHONY: check-all docker-build docker-up container-build

help:
	@echo "Country Compare targets:"
	@echo "  make install          Install main app dependencies"
	@echo "  make install-dev      Install main app with dev dependencies"
	@echo "  make test             Run main app tests"
	@echo "  make lint             Run main app ruff"
	@echo "  make lint-fix         Run main app ruff --fix"
	@echo "  make format           Run main app black"
	@echo "  make format-check     Check main app black formatting"
	@echo "  make typecheck        Run main app mypy"
	@echo "  make check            Run main app lint, format-check, typecheck, and tests"
	@echo "  make llm-check        Run LLM service checks"
	@echo "  make check-all        Run main app and LLM service checks"
	@echo "  make docker-build     Build Docker Compose services"
	@echo "  make docker-up        Start Docker Compose stack"

install:
	$(PYTHON) -m pip install -r requirements-dev.txt

install-dev:
	$(PYTHON) -m pip install -e ".[dev]"

format:
	$(PYTHON) -m black $(APP_PACKAGE_DIR) $(APP_TEST_DIR) $(SCRIPT_DIR)

format-check:
	$(PYTHON) -m black --check $(APP_PACKAGE_DIR) $(APP_TEST_DIR) $(SCRIPT_DIR)

lint:
	$(PYTHON) -m ruff check $(APP_PACKAGE_DIR) $(APP_TEST_DIR) $(SCRIPT_DIR)

lint-fix:
	$(PYTHON) -m ruff check --fix $(APP_PACKAGE_DIR) $(APP_TEST_DIR) $(SCRIPT_DIR)

typecheck:
	$(PYTHON) -m mypy $(APP_PACKAGE_DIR)

test:
	$(PYTHON) -m pytest

check: lint format-check typecheck test

check-strict: check

clean:
	$(PYTHON) -c "import shutil, pathlib; [shutil.rmtree(p, ignore_errors=True) for p in pathlib.Path('.').rglob('__pycache__')]"
	$(PYTHON) -c "import shutil; [shutil.rmtree(p, ignore_errors=True) for p in ['.pytest_cache', '.mypy_cache', '.ruff_cache']]"

llm-install:
	$(MAKE) -C $(LLM_SERVICE_DIR) install

llm-install-dev:
	$(MAKE) -C $(LLM_SERVICE_DIR) install-dev

llm-test:
	$(MAKE) -C $(LLM_SERVICE_DIR) test

llm-lint:
	$(MAKE) -C $(LLM_SERVICE_DIR) lint

llm-format:
	$(MAKE) -C $(LLM_SERVICE_DIR) format

llm-format-check:
	$(MAKE) -C $(LLM_SERVICE_DIR) format-check

llm-typecheck:
	$(MAKE) -C $(LLM_SERVICE_DIR) typecheck

llm-check:
	$(MAKE) -C $(LLM_SERVICE_DIR) check

llm-run:
	$(MAKE) -C $(LLM_SERVICE_DIR) run

llm-run-dev:
	$(MAKE) -C $(LLM_SERVICE_DIR) run-dev

check-all: check llm-check

docker-build:
	docker compose build

container-build: docker-build

docker-up:
	docker compose up --build