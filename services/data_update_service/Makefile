PYTHON ?= python
SERVICE_ROOT := $(abspath .)
REPO_ROOT := $(abspath ../..)
PACKAGE_SRC := $(SERVICE_ROOT)/src
PROJECT_SRC := $(REPO_ROOT)/src
PACKAGE_DIR := src/data_update_service
TEST_DIR := tests

ifeq ($(OS),Windows_NT)
PYTHONPATH_SEPARATOR := ;
else
PYTHONPATH_SEPARATOR := :
endif

export PYTHONPATH := $(PACKAGE_SRC)$(PYTHONPATH_SEPARATOR)$(PROJECT_SRC)

SOURCE_FAMILY ?= world_bank
MANIFEST_PATH ?= config/source_manifests/world_bank_real_data.yaml
MODE ?= full_refresh
DRY_RUN ?= true
PUBLISH ?= false
PROMOTE ?= false
PROMOTION_CHANNEL ?= staging
REQUESTED_BY ?= make
ARTIFACT_ROOT ?= data/artifacts/data_update
AUDIT_ROOT ?= data/audit/data_update
OUTPUT_JSON ?= data/audit/data_update/latest_refresh_result.json


.PHONY: help install install-dev install-kafka test lint lint-fix format format-check typecheck check check-strict run run-dev refresh-dry-run refresh-artifact run-worker clean

help:
	@echo "Data Update Service targets:"
	@echo "  make install           Install service runtime dependencies"
	@echo "  make install-dev       Install service with dev dependencies"
	@echo "  make install-kafka     Install service with Kafka runtime dependency"
	@echo "  make test              Run service tests"
	@echo "  make lint              Run ruff"
	@echo "  make lint-fix          Run ruff with --fix"
	@echo "  make format            Run black"
	@echo "  make format-check      Check black formatting"
	@echo "  make typecheck         Run mypy"
	@echo "  make check             Run lint, format-check, typecheck, and tests"
	@echo "  make run               Run a dry-run refresh through the shared CLI"
	@echo "  make run-dev           Alias for make run"
	@echo "  make refresh-dry-run   Run a dry-run refresh through the shared CLI"
	@echo "  make refresh-artifact  Run a local filesystem artifact refresh"
	@echo "  make run-worker        Run the Kafka worker entrypoint"
	@echo "  make clean             Remove local caches"

install:
	$(PYTHON) -m pip install .

install-dev:
	$(PYTHON) -m pip install -e ".[dev]"

install-kafka:
	$(PYTHON) -m pip install -e ".[kafka]"

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

run: refresh-dry-run

run-dev: refresh-dry-run

refresh-dry-run:
	cd "$(REPO_ROOT)" && $(PYTHON) -m data_update_service.cli refresh --source-family $(SOURCE_FAMILY) --manifest-path $(MANIFEST_PATH) --mode $(MODE) --dry-run true --publish false --promote false --promotion-channel $(PROMOTION_CHANNEL) --requested-by $(REQUESTED_BY) --artifact-root $(ARTIFACT_ROOT) --audit-root $(AUDIT_ROOT) --output-json $(OUTPUT_JSON)

refresh-artifact:
	cd "$(REPO_ROOT)" && $(PYTHON) -m data_update_service.cli refresh --source-family $(SOURCE_FAMILY) --manifest-path $(MANIFEST_PATH) --mode $(MODE) --dry-run false --publish true --promote $(PROMOTE) --promotion-channel $(PROMOTION_CHANNEL) --requested-by $(REQUESTED_BY) --artifact-root $(ARTIFACT_ROOT) --audit-root $(AUDIT_ROOT) --output-json $(OUTPUT_JSON)

run-worker:
	cd "$(REPO_ROOT)" && $(PYTHON) -m data_update_service.worker.consumer

clean:
	$(PYTHON) -c "import shutil, pathlib; [shutil.rmtree(p, ignore_errors=True) for p in pathlib.Path('.').rglob('__pycache__')]"
	$(PYTHON) -c "import shutil, pathlib; [shutil.rmtree(p, ignore_errors=True) for p in [pathlib.Path('.pytest_cache'), pathlib.Path('.mypy_cache'), pathlib.Path('.ruff_cache'), *pathlib.Path('src').glob('*.egg-info')]]"
