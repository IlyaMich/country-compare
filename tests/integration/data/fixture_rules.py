from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

FIXTURE_DATA_DIR = Path("tests/fixtures/data")


def load_yaml_fixture(filename: str) -> dict[str, Any]:
    """Load a YAML mapping from tests/fixtures/data.

    These fixtures are release-test rules, not production config.
    """
    path = FIXTURE_DATA_DIR / filename

    if not path.exists():
        raise AssertionError(f"Missing required data correctness fixture: {path}")

    with path.open("r", encoding="utf-8") as file:
        loaded = yaml.safe_load(file) or {}

    if not isinstance(loaded, dict):
        raise AssertionError(f"{path} must contain a YAML mapping/object.")

    return loaded


def as_list(value: object) -> list[str]:
    """Normalize a scalar/list/None YAML value into a list of strings."""
    if value is None:
        return []

    if isinstance(value, list):
        return [str(item) for item in value]

    return [str(value)]


def normalize_text(value: object) -> str:
    """Normalize text for case-insensitive contains checks."""
    return str(value).strip().lower()
