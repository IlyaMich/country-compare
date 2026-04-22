from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import os


@dataclass(frozen=True)
class AppContext:
    """
    Framework-neutral runtime context for app/service wiring.

    The defaults intentionally match the current project layout while allowing
    overrides through environment variables or explicit constructor arguments.
    """

    metrics_config_path: Path = Path("config/metrics.yaml")
    scoring_config_path: Path = Path("config/scoring_profiles.yaml")
    store_backend: str = "parquet"
    store_path: Path | None = None
    debug: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(self, "metrics_config_path", Path(self.metrics_config_path).expanduser())
        object.__setattr__(self, "scoring_config_path", Path(self.scoring_config_path).expanduser())
        object.__setattr__(self, "store_path", None if self.store_path is None else Path(self.store_path).expanduser())
        object.__setattr__(self, "store_backend", self.store_backend.strip().lower())

    @classmethod
    def from_env(cls) -> AppContext:
        metrics_config_path = os.getenv("COUNTRY_COMPARE_METRICS_CONFIG", "config/metrics.yaml")
        scoring_config_path = os.getenv("COUNTRY_COMPARE_SCORING_CONFIG", "config/scoring_profiles.yaml")
        store_backend = os.getenv("COUNTRY_COMPARE_STORE_BACKEND", "parquet")
        store_path_raw = os.getenv("COUNTRY_COMPARE_STORE_PATH")
        debug_raw = os.getenv("COUNTRY_COMPARE_DEBUG", "false").strip().lower()

        return cls(
            metrics_config_path=Path(metrics_config_path),
            scoring_config_path=Path(scoring_config_path),
            store_backend=store_backend,
            store_path=Path(store_path_raw) if store_path_raw else None,
            debug=debug_raw in {"1", "true", "yes", "on"},
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
