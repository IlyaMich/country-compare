.PHONY: install format format-check lint lint-fix test

install:
	python -m pip install -r requirements-dev.txt

format:
	python -m black country_compare tests

format-check:
	python -m black --check country_compare tests

lint:
	python -m ruff check country_compare tests

lint-fix:
	python -m ruff check --fix country_compare tests

test:
	python -m pytest