from __future__ import annotations

import importlib

from country_compare import paths


def test_package_imports() -> None:
    module = importlib.import_module("country_compare")

    assert module is not None


def test_api_app_imports() -> None:
    module = importlib.import_module("country_compare.api.main")

    assert hasattr(module, "create_app")


def test_cli_imports() -> None:
    module = importlib.import_module("country_compare.cli.main")

    assert hasattr(module, "main")


def test_project_paths_resolve_to_repository_root() -> None:
    assert paths.PACKAGE_ROOT.name == "country_compare"
    assert paths.PACKAGE_ROOT.parent.name == "src"
    assert paths.CONFIG_DIR == paths.PROJECT_ROOT / "config"
    assert paths.DATA_DIR == paths.PROJECT_ROOT / "data"
