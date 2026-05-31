from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from country_compare.settings import AppSettings, load_app_settings
from country_compare.settings.defaults import (
    DEFAULT_AUDIT_DIR,
    DEFAULT_DEBUG,
    DEFAULT_EXPORT_DIR,
    DEFAULT_METRICS_CONFIG_PATH,
    DEFAULT_SCORING_CONFIG_PATH,
    DEFAULT_STORE_BACKEND,
    DEFAULT_STORE_PATH,
)
from country_compare.settings.models import PathSettings


@dataclass(frozen=True)
class AppContext:
    """Framework-neutral runtime context for app/service wiring.

    Existing public fields are preserved for backward compatibility. New runtime/product
    settings are available through ``settings`` and selected convenience fields.
    """

    metrics_config_path: Path = DEFAULT_METRICS_CONFIG_PATH
    scoring_config_path: Path = DEFAULT_SCORING_CONFIG_PATH
    store_backend: str = DEFAULT_STORE_BACKEND
    store_path: Path | None = DEFAULT_STORE_PATH
    debug: bool = DEFAULT_DEBUG
    audit_dir: Path = DEFAULT_AUDIT_DIR
    export_dir: Path = DEFAULT_EXPORT_DIR
    settings: AppSettings | None = None

    def __post_init__(self) -> None:
        settings = self.settings or AppSettings(
            paths=PathSettings(
                metrics_config_path=self.metrics_config_path,
                scoring_config_path=self.scoring_config_path,
                store_backend=self.store_backend,
                store_path=self.store_path,
                audit_dir=self.audit_dir,
                export_dir=self.export_dir,
            ),
            debug=self.debug,
        )

        resolved_paths = PathSettings(
            metrics_config_path=_resolve_runtime_path(
                settings.paths.metrics_config_path
            ),
            scoring_config_path=_resolve_runtime_path(
                settings.paths.scoring_config_path
            ),
            store_backend=settings.paths.store_backend,
            store_path=_resolve_optional_runtime_path(settings.paths.store_path),
            audit_dir=_resolve_runtime_path(settings.paths.audit_dir),
            export_dir=_resolve_runtime_path(settings.paths.export_dir),
        )

        _validate_required_file(resolved_paths.metrics_config_path, "Metrics config")
        _validate_required_file(
            resolved_paths.scoring_config_path, "Scoring profiles config"
        )

        resolved_settings = AppSettings(
            paths=resolved_paths,
            ui=settings.ui,
            prediction=settings.prediction,
            debug=settings.debug,
        )

        object.__setattr__(self, "settings", resolved_settings)
        object.__setattr__(
            self, "metrics_config_path", resolved_paths.metrics_config_path
        )
        object.__setattr__(
            self, "scoring_config_path", resolved_paths.scoring_config_path
        )
        object.__setattr__(self, "store_backend", resolved_paths.store_backend)
        object.__setattr__(self, "store_path", resolved_paths.store_path)
        object.__setattr__(self, "audit_dir", resolved_paths.audit_dir)
        object.__setattr__(self, "export_dir", resolved_paths.export_dir)
        object.__setattr__(self, "debug", resolved_settings.debug)

    @classmethod
    def from_env(cls) -> AppContext:
        settings = load_app_settings()
        return cls(
            metrics_config_path=settings.paths.metrics_config_path,
            scoring_config_path=settings.paths.scoring_config_path,
            store_backend=settings.paths.store_backend,
            store_path=settings.paths.store_path,
            audit_dir=settings.paths.audit_dir,
            export_dir=settings.paths.export_dir,
            debug=settings.debug,
            settings=settings,
        )

    @property
    def metrics_config_abspath(self) -> Path:
        return self.metrics_config_path.resolve()

    @property
    def scoring_config_abspath(self) -> Path:
        return self.scoring_config_path.resolve()

    @property
    def store_abspath(self) -> Path | None:
        return None if self.store_path is None else self.store_path.resolve()


def _resolve_runtime_path(path: str | Path) -> Path:
    """Resolve runtime paths deterministically for services."""
    return Path(path).expanduser().resolve()


def _resolve_optional_runtime_path(path: str | Path | None) -> Path | None:
    if path is None or str(path).strip() == "":
        return None
    return _resolve_runtime_path(path)


def _validate_required_file(path: Path, description: str) -> None:
    if not path.is_file():
        raise FileNotFoundError(
            f"{description} does not exist or is not a file: {path}"
        )
