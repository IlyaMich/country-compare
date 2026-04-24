from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from country_compare.settings.defaults import (
    DEFAULT_AUDIT_DIR,
    DEFAULT_DEBUG,
    DEFAULT_EXPORT_DIR,
    DEFAULT_MAX_PREDICTION_HORIZON,
    DEFAULT_METRICS_CONFIG_PATH,
    DEFAULT_MOVING_AVERAGE_WINDOW_SIZE,
    DEFAULT_PREDICTION_FALLBACK_METHOD,
    DEFAULT_PREDICTION_METHOD,
    DEFAULT_SCORING_CONFIG_PATH,
    DEFAULT_STORE_BACKEND,
    DEFAULT_STORE_PATH,
    DEFAULT_UI_APP_TITLE,
    DEFAULT_UI_DEFAULT_PAGE,
    DEFAULT_UI_LAYOUT,
    DEFAULT_UI_PAGE_ICON,
    DEFAULT_UI_PAGE_TITLE,
)


def _coerce_path(value: str | Path) -> Path:
    return Path(value).expanduser()


def _coerce_optional_path(value: str | Path | None) -> Path | None:
    if value is None or str(value).strip() == "":
        return None
    return _coerce_path(value)


@dataclass(frozen=True, slots=True)
class PathSettings:
    metrics_config_path: Path = DEFAULT_METRICS_CONFIG_PATH
    scoring_config_path: Path = DEFAULT_SCORING_CONFIG_PATH
    store_backend: str = DEFAULT_STORE_BACKEND
    store_path: Path | None = DEFAULT_STORE_PATH
    audit_dir: Path = DEFAULT_AUDIT_DIR
    export_dir: Path = DEFAULT_EXPORT_DIR

    def __post_init__(self) -> None:
        object.__setattr__(self, "metrics_config_path", _coerce_path(self.metrics_config_path))
        object.__setattr__(self, "scoring_config_path", _coerce_path(self.scoring_config_path))
        object.__setattr__(self, "store_backend", str(self.store_backend).strip().lower())
        object.__setattr__(self, "store_path", _coerce_optional_path(self.store_path))
        object.__setattr__(self, "audit_dir", _coerce_path(self.audit_dir))
        object.__setattr__(self, "export_dir", _coerce_path(self.export_dir))


@dataclass(frozen=True, slots=True)
class UISettings:
    app_title: str = DEFAULT_UI_APP_TITLE
    page_title: str = DEFAULT_UI_PAGE_TITLE
    page_icon: str = DEFAULT_UI_PAGE_ICON
    layout: str = DEFAULT_UI_LAYOUT
    default_page: str = DEFAULT_UI_DEFAULT_PAGE

    def __post_init__(self) -> None:
        object.__setattr__(self, "app_title", str(self.app_title).strip() or DEFAULT_UI_APP_TITLE)
        object.__setattr__(self, "page_title", str(self.page_title).strip() or DEFAULT_UI_PAGE_TITLE)
        object.__setattr__(self, "page_icon", str(self.page_icon))
        object.__setattr__(self, "layout", str(self.layout).strip() or DEFAULT_UI_LAYOUT)
        object.__setattr__(self, "default_page", str(self.default_page).strip() or DEFAULT_UI_DEFAULT_PAGE)


@dataclass(frozen=True, slots=True)
class PredictionSettings:
    default_method: str = DEFAULT_PREDICTION_METHOD
    fallback_method: str | None = DEFAULT_PREDICTION_FALLBACK_METHOD
    max_horizon_years: int = DEFAULT_MAX_PREDICTION_HORIZON
    moving_average_window_size: int = DEFAULT_MOVING_AVERAGE_WINDOW_SIZE

    def __post_init__(self) -> None:
        object.__setattr__(self, "default_method", str(self.default_method).strip())
        fallback = None if self.fallback_method is None else str(self.fallback_method).strip()
        object.__setattr__(self, "fallback_method", fallback or None)
        object.__setattr__(self, "max_horizon_years", int(self.max_horizon_years))
        object.__setattr__(self, "moving_average_window_size", int(self.moving_average_window_size))


@dataclass(frozen=True, slots=True)
class AppSettings:
    paths: PathSettings = field(default_factory=PathSettings)
    ui: UISettings = field(default_factory=UISettings)
    prediction: PredictionSettings = field(default_factory=PredictionSettings)
    debug: bool = DEFAULT_DEBUG