from __future__ import annotations

import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
PYPROJECT = ROOT / "pyproject.toml"


def _pyproject() -> dict:
    return tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))


def _dependency_blob(dependencies: list[str]) -> str:
    return "\n".join(dependencies).lower()


def test_base_dependencies_exclude_api_ui_and_chart_footprint() -> None:
    project = _pyproject()["project"]
    dependency_blob = _dependency_blob(project["dependencies"])

    assert "fastapi" not in dependency_blob
    assert "uvicorn" not in dependency_blob
    assert "httpx" not in dependency_blob
    assert "streamlit" not in dependency_blob
    assert "matplotlib" not in dependency_blob


def test_api_extra_owns_backend_dependencies() -> None:
    optional_dependencies = _pyproject()["project"]["optional-dependencies"]
    api_blob = _dependency_blob(optional_dependencies["api"])

    assert "fastapi" in api_blob
    assert "uvicorn" in api_blob
    assert "streamlit" not in api_blob
    assert "matplotlib" not in api_blob


def test_ui_extra_owns_ui_http_and_chart_dependencies() -> None:
    optional_dependencies = _pyproject()["project"]["optional-dependencies"]
    ui_blob = _dependency_blob(optional_dependencies["ui"])

    assert "streamlit" in ui_blob
    assert "httpx" in ui_blob
    assert "matplotlib" in ui_blob
    assert "fastapi" not in ui_blob
    assert "uvicorn" not in ui_blob


def test_dev_extra_includes_api_ui_and_test_dependencies() -> None:
    optional_dependencies = _pyproject()["project"]["optional-dependencies"]
    dev_blob = _dependency_blob(optional_dependencies["dev"])

    for dependency_name in (
        "fastapi",
        "uvicorn",
        "httpx",
        "matplotlib",
        "streamlit",
        "pytest",
        "ruff",
        "black",
        "mypy",
    ):
        assert dependency_name in dev_blob
