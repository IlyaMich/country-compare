from __future__ import annotations

import os
from dataclasses import dataclass

from country_compare import __version__


@dataclass(frozen=True)
class ApiSettings:
    """API-only settings.

    Project/domain settings remain owned by ``country_compare.settings`` and
    ``AppContext``. These values only control the HTTP adapter.
    """

    api_version: str = __version__
    cors_origins: tuple[str, ...] = ("http://localhost:8501",)
    max_records: int = 500
    max_countries: int = 50
    max_metrics: int = 50
    max_horizon_years: int = 10
    max_holdout_years: int = 10
    max_top_n: int = 100
    enable_docs: bool = True
    api_key: str | None = None
    log_level: str = "INFO"

    @classmethod
    def from_env(cls) -> ApiSettings:
        return cls(
            cors_origins=_parse_csv_env("COUNTRY_COMPARE_API_CORS_ORIGINS"),
            max_records=_parse_int_env("COUNTRY_COMPARE_API_MAX_RECORDS", default=500),
            max_countries=_parse_int_env(
                "COUNTRY_COMPARE_API_MAX_COUNTRIES", default=50
            ),
            max_metrics=_parse_int_env("COUNTRY_COMPARE_API_MAX_METRICS", default=50),
            max_horizon_years=_parse_int_env(
                "COUNTRY_COMPARE_API_MAX_HORIZON_YEARS", default=10
            ),
            max_holdout_years=_parse_int_env(
                "COUNTRY_COMPARE_API_MAX_HOLDOUT_YEARS", default=10
            ),
            max_top_n=_parse_int_env("COUNTRY_COMPARE_API_MAX_TOP_N", default=100),
            enable_docs=_parse_bool_env(
                "COUNTRY_COMPARE_API_ENABLE_DOCS", default=True
            ),
            api_key=_parse_optional_env("COUNTRY_COMPARE_API_KEY"),
            log_level=_parse_optional_env("COUNTRY_COMPARE_API_LOG_LEVEL") or "INFO",
        )


def _parse_optional_env(name: str) -> str | None:
    value = os.getenv(name)
    if value is None:
        return None

    stripped = value.strip()
    return stripped or None


def _parse_csv_env(name: str) -> tuple[str, ...]:
    raw_value = os.environ.get(name)
    if raw_value is None:
        return ApiSettings.cors_origins

    return tuple(value.strip() for value in raw_value.split(",") if value.strip())


def _parse_int_env(name: str, *, default: int) -> int:
    raw_value = os.environ.get(name)
    if raw_value is None or not raw_value.strip():
        return default

    try:
        value = int(raw_value)
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer.") from exc

    if value <= 0:
        raise ValueError(f"{name} must be greater than zero.")
    return value


def _parse_bool_env(name: str, *, default: bool) -> bool:
    raw_value = os.environ.get(name)
    if raw_value is None or not raw_value.strip():
        return default

    normalized = raw_value.strip().lower()
    if normalized in {"1", "true", "yes", "y", "on"}:
        return True
    if normalized in {"0", "false", "no", "n", "off"}:
        return False

    raise ValueError(f"{name} must be a boolean value.")
