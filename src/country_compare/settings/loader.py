from __future__ import annotations

import os
from dataclasses import replace
from pathlib import Path
from typing import Any

import yaml

from country_compare.settings.defaults import DEFAULT_APP_CONFIG_PATH
from country_compare.settings.models import (
    AppSettings,
    PathSettings,
    PredictionSettings,
    UISettings,
)

_TRUE_VALUES = {"1", "true", "yes", "on"}
_FALSE_VALUES = {"0", "false", "no", "off"}

_PATH_KEYS = {
    "metrics_config_path",
    "scoring_config_path",
    "store_backend",
    "store_path",
    "audit_dir",
    "export_dir",
}
_UI_KEYS = {"app_title", "page_title", "page_icon", "layout", "default_page"}
_PREDICTION_KEYS = {
    "default_method",
    "fallback_method",
    "max_horizon_years",
    "moving_average_window_size",
}


def load_app_settings(
    *,
    app_config_path: str | Path | None = None,
    metrics_config_path: str | Path | None = None,
    scoring_config_path: str | Path | None = None,
    store_backend: str | None = None,
    store_path: str | Path | None = None,
    audit_dir: str | Path | None = None,
    export_dir: str | Path | None = None,
    debug: bool | str | None = None,
    ui_app_title: str | None = None,
    ui_page_title: str | None = None,
    ui_page_icon: str | None = None,
    ui_layout: str | None = None,
    ui_default_page: str | None = None,
    prediction_default_method: str | None = None,
    prediction_fallback_method: str | None = None,
    max_prediction_horizon: int | str | None = None,
    moving_average_window_size: int | str | None = None,
) -> AppSettings:
    """Load runtime/product settings.

    Precedence, highest to lowest:
    explicit function arguments -> environment variables -> optional config/app.yaml -> \
    code defaults.
    """

    config_path = _resolve_app_config_path(app_config_path)
    settings = _settings_from_mapping(_read_optional_yaml(config_path))
    settings = _apply_flat_overrides(settings, _environment_overrides())
    settings = _apply_flat_overrides(
        settings,
        {
            "metrics_config_path": metrics_config_path,
            "scoring_config_path": scoring_config_path,
            "store_backend": store_backend,
            "store_path": store_path,
            "audit_dir": audit_dir,
            "export_dir": export_dir,
            "debug": debug,
            "app_title": ui_app_title,
            "page_title": ui_page_title,
            "page_icon": ui_page_icon,
            "layout": ui_layout,
            "default_page": ui_default_page,
            "default_method": prediction_default_method,
            "fallback_method": prediction_fallback_method,
            "max_horizon_years": max_prediction_horizon,
            "moving_average_window_size": moving_average_window_size,
        },
    )
    return settings


def _resolve_app_config_path(app_config_path: str | Path | None) -> Path:
    env_path = os.getenv("COUNTRY_COMPARE_APP_CONFIG")
    return Path(app_config_path or env_path or DEFAULT_APP_CONFIG_PATH).expanduser()


def _read_optional_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    if not isinstance(data, dict):
        raise ValueError(f"Expected top-level mapping in app settings file: {path}")
    return data


def _settings_from_mapping(raw: dict[str, Any]) -> AppSettings:
    path_data = dict(raw.get("paths") or {})
    ui_data = dict(raw.get("ui") or {})
    prediction_data = dict(raw.get("prediction") or {})

    for key in _PATH_KEYS:
        if key in raw and key not in path_data:
            path_data[key] = raw[key]
    for key in _UI_KEYS:
        if key in raw and key not in ui_data:
            ui_data[key] = raw[key]
    for key in _PREDICTION_KEYS:
        if key in raw and key not in prediction_data:
            prediction_data[key] = raw[key]

    return AppSettings(
        paths=PathSettings(**path_data),
        ui=UISettings(**ui_data),
        prediction=PredictionSettings(**prediction_data),
        debug=_coerce_bool(raw.get("debug", False)),
    )


def _environment_overrides() -> dict[str, Any]:
    return {
        "metrics_config_path": os.getenv("COUNTRY_COMPARE_METRICS_CONFIG"),
        "scoring_config_path": os.getenv("COUNTRY_COMPARE_SCORING_CONFIG"),
        "store_backend": os.getenv("COUNTRY_COMPARE_STORE_BACKEND"),
        "store_path": os.getenv("COUNTRY_COMPARE_STORE_PATH"),
        "audit_dir": os.getenv("COUNTRY_COMPARE_AUDIT_DIR"),
        "export_dir": os.getenv("COUNTRY_COMPARE_EXPORT_DIR"),
        "debug": os.getenv("COUNTRY_COMPARE_DEBUG"),
        "app_title": os.getenv("COUNTRY_COMPARE_UI_APP_TITLE"),
        "page_title": os.getenv("COUNTRY_COMPARE_UI_PAGE_TITLE"),
        "page_icon": os.getenv("COUNTRY_COMPARE_UI_PAGE_ICON"),
        "layout": os.getenv("COUNTRY_COMPARE_UI_LAYOUT"),
        "default_page": os.getenv("COUNTRY_COMPARE_UI_DEFAULT_PAGE"),
        "default_method": os.getenv("COUNTRY_COMPARE_PREDICTION_METHOD"),
        "fallback_method": os.getenv("COUNTRY_COMPARE_PREDICTION_FALLBACK_METHOD"),
        "max_horizon_years": os.getenv("COUNTRY_COMPARE_MAX_PREDICTION_HORIZON"),
        "moving_average_window_size": os.getenv(
            "COUNTRY_COMPARE_MOVING_AVERAGE_WINDOW_SIZE"
        ),
    }


def _apply_flat_overrides(
    settings: AppSettings, overrides: dict[str, Any]
) -> AppSettings:
    clean = {key: value for key, value in overrides.items() if value is not None}
    if not clean:
        return settings

    path_updates = {key: clean[key] for key in _PATH_KEYS if key in clean}
    ui_updates = {key: clean[key] for key in _UI_KEYS if key in clean}
    prediction_updates = {key: clean[key] for key in _PREDICTION_KEYS if key in clean}

    debug = settings.debug
    if "debug" in clean:
        debug = _coerce_bool(clean["debug"])

    return AppSettings(
        paths=replace(settings.paths, **path_updates),
        ui=replace(settings.ui, **ui_updates),
        prediction=replace(settings.prediction, **prediction_updates),
        debug=debug,
    )


def _coerce_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if text in _TRUE_VALUES:
        return True
    if text in _FALSE_VALUES or text == "":
        return False
    raise ValueError(f"Expected boolean-like value, got {value!r}")
