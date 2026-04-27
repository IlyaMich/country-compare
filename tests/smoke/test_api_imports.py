from __future__ import annotations

import builtins
import importlib
import sys
from typing import Any

import pytest
from fastapi import FastAPI


def test_api_main_imports_without_streamlit_ui(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sys.modules.pop("country_compare.api.main", None)

    api_package = sys.modules.get("country_compare.api")
    if api_package is not None:
        monkeypatch.delattr(api_package, "main", raising=False)

    modules_before = set(sys.modules)

    original_import = builtins.__import__

    def guarded_import(
        name: str,
        globals: dict[str, Any] | None = None,
        locals: dict[str, Any] | None = None,
        fromlist: tuple[str, ...] = (),
        level: int = 0,
    ) -> Any:
        if name == "streamlit" or name.startswith("streamlit."):
            raise AssertionError("API import must not import Streamlit")

        if name == "country_compare.ui" or name.startswith("country_compare.ui."):
            raise AssertionError("API import must not import the Streamlit UI package")

        return original_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", guarded_import)

    main = importlib.import_module("country_compare.api.main")

    assert callable(main.create_app)

    app = main.create_app()

    assert isinstance(app, FastAPI)
    assert main.app is not None

    modules_after = set(sys.modules)
    newly_imported_modules = modules_after - modules_before

    assert "streamlit" not in newly_imported_modules
    assert not any(
        module_name == "streamlit" or module_name.startswith("streamlit.")
        for module_name in newly_imported_modules
    )
    assert not any(
        module_name == "country_compare.ui"
        or module_name.startswith("country_compare.ui.")
        for module_name in newly_imported_modules
    )
