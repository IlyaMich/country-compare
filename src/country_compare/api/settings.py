from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class ApiSettings:
    """API-only settings.

    Project/domain settings remain owned by ``country_compare.settings`` and
    ``AppContext``. These values only control the HTTP adapter.
    """

    cors_origins: tuple[str, ...] = ()
    max_records: int = 500
    enable_docs: bool = True

    @classmethod
    def from_env(cls) -> ApiSettings:
        return cls(
            cors_origins=_parse_csv_env("COUNTRY_COMPARE_API_CORS_ORIGINS"),
            max_records=_parse_int_env("COUNTRY_COMPARE_API_MAX_RECORDS", default=500),
            enable_docs=_parse_bool_env(
                "COUNTRY_COMPARE_API_ENABLE_DOCS", default=True
            ),
        )


def _parse_csv_env(name: str) -> tuple[str, ...]:
    raw_value = os.environ.get(name, "")
    return tuple(value.strip() for value in raw_value.split(",") if value.strip())


def _parse_int_env(name: str, *, default: int) -> int:
    raw_value = os.environ.get(name)
    if raw_value is None or not raw_value.strip():
        return default

    try:
        return int(raw_value)
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer.") from exc


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
