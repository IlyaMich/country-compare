.PHONY: install format format-check lint lint-fix test type-check check check-strict container-build container-up container-down container-logs container-ps

PYTHON := python
DOCKER ?= docker
COMPOSE ?= $(DOCKER) compose
PACKAGE_DIRS := src/country_compare tests scripts

install:
	$(PYTHON) -m pip install -r requirements-dev.txt

format:
	$(PYTHON) -m black $(PACKAGE_DIRS)

format-check:
	$(PYTHON) -m black --check $(PACKAGE_DIRS)

lint:
	$(PYTHON) -m ruff check $(PACKAGE_DIRS)

lint-fix:
	$(PYTHON) -m ruff check --fix $(PACKAGE_DIRS)

test:
	$(PYTHON) -m pytest

type-check:
	$(PYTHON) -m mypy src/country_compare

check: format-check lint test

check-strict: check type-check

container-build:
	$(COMPOSE) build

container-up:
	$(COMPOSE) up --build

container-down:
	$(COMPOSE) down

container-logs:
	$(COMPOSE) logs -f

container-ps:
	$(COMPOSE) ps