from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from country_compare.settings import AppSettings, load_app_settings
from country_compare.settings.defaults import DEFAULT_DEBUG, DEFAULT_STORE_BACKEND
from country_compare.settings.models import PathSettings


@dataclass(frozen=True)
class AppContext:
    """Framework-neutral runtime context for app/service wiring.

    Existing public fields are preserved for backward compatibility. New runtime/product
    settings are available through ``settings`` and selected convenience fields.
    """

    metrics_config_path: Path = Path("config/metrics.yaml")
    scoring_config_path: Path = Path("config/scoring_profiles.yaml")
    store_backend: str = DEFAULT_STORE_BACKEND
    store_path: Path | None = None
    debug: bool = DEFAULT_DEBUG
    audit_dir: Path = Path("data/audit")
    export_dir: Path = Path("data/exports")
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
        object.__setattr__(self, "settings", settings)
        object.__setattr__(
            self, "metrics_config_path", settings.paths.metrics_config_path
        )
        object.__setattr__(
            self, "scoring_config_path", settings.paths.scoring_config_path
        )
        object.__setattr__(self, "store_backend", settings.paths.store_backend)
        object.__setattr__(self, "store_path", settings.paths.store_path)
        object.__setattr__(self, "audit_dir", settings.paths.audit_dir)
        object.__setattr__(self, "export_dir", settings.paths.export_dir)
        object.__setattr__(self, "debug", settings.debug)

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
