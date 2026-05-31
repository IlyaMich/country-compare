from __future__ import annotations

import os
from dataclasses import dataclass, field

from country_compare import __version__

RuntimeEnv = str
LogFormat = str

_RUNTIME_ENVS = {"development", "test", "production"}
_LOG_FORMATS = {"json", "plain"}
_LOG_LEVELS = {"CRITICAL", "ERROR", "WARNING", "INFO", "DEBUG", "NOTSET"}

_NUMERIC_BOUNDS: dict[str, tuple[str, int, int]] = {
    "max_records": ("COUNTRY_COMPARE_API_MAX_RECORDS", 500, 10_000),
    "max_countries": ("COUNTRY_COMPARE_API_MAX_COUNTRIES", 50, 250),
    "max_metrics": ("COUNTRY_COMPARE_API_MAX_METRICS", 50, 500),
    "max_horizon_years": ("COUNTRY_COMPARE_API_MAX_HORIZON_YEARS", 10, 50),
    "max_holdout_years": ("COUNTRY_COMPARE_API_MAX_HOLDOUT_YEARS", 10, 50),
    "max_top_n": ("COUNTRY_COMPARE_API_MAX_TOP_N", 100, 500),
}


@dataclass(frozen=True)
class ApiSettings:
    """API-only settings.

    Project/domain settings remain owned by ``country_compare.settings`` and
    ``AppContext``. These values only control the HTTP adapter.
    """

    api_version: str = __version__
    runtime_env: RuntimeEnv = "development"
    cors_origins: tuple[str, ...] = ("http://localhost:8501",)

    max_records: int = 500
    max_countries: int = 50
    max_metrics: int = 50
    max_horizon_years: int = 10
    max_holdout_years: int = 10
    max_top_n: int = 100

    enable_docs: bool = True
    protect_docs: bool = False
    enable_metrics: bool = False
    protect_metrics: bool = True

    api_key: str | None = field(default=None, repr=False)
    auth_required: bool = False
    protected_prefixes: tuple[str, ...] = ("/api/v1", "/ready")
    public_paths: tuple[str, ...] = ("/health", "/docs", "/redoc", "/openapi.json")

    log_level: str = "INFO"
    configure_logging: bool = True
    log_format: LogFormat = "json"
    log_propagate: bool = True
    log_clear_handlers: bool = False

    def __post_init__(self) -> None:
        normalized_env = self.runtime_env.strip().lower()
        if normalized_env not in _RUNTIME_ENVS:
            raise ValueError(
                "COUNTRY_COMPARE_API_ENV must be one of: "
                f"{', '.join(sorted(_RUNTIME_ENVS))}."
            )
        object.__setattr__(self, "runtime_env", normalized_env)

        normalized_level = self.log_level.strip().upper()
        if normalized_level not in _LOG_LEVELS:
            raise ValueError(
                "COUNTRY_COMPARE_API_LOG_LEVEL must be one of: "
                f"{', '.join(sorted(_LOG_LEVELS))}."
            )
        object.__setattr__(self, "log_level", normalized_level)

        normalized_format = self.log_format.strip().lower()
        if normalized_format not in _LOG_FORMATS:
            raise ValueError(
                "COUNTRY_COMPARE_API_LOG_FORMAT must be one of: "
                f"{', '.join(sorted(_LOG_FORMATS))}."
            )
        object.__setattr__(self, "log_format", normalized_format)

        for field_name, (env_name, _default, upper_bound) in _NUMERIC_BOUNDS.items():
            value = getattr(self, field_name)
            if value <= 0:
                raise ValueError(f"{env_name} must be greater than zero.")
            if value > upper_bound:
                raise ValueError(
                    f"{env_name} must be less than or equal to {upper_bound}."
                )

        if self.auth_required and not self.api_key:
            raise ValueError(
                "COUNTRY_COMPARE_API_KEY must be set when API authentication is "
                "required. Set COUNTRY_COMPARE_API_ENV=development for local "
                "unauthenticated development, or set COUNTRY_COMPARE_API_AUTH_REQUIRED=false "
                "only for explicitly accepted non-production deployments."
            )

    @property
    def auth_enabled(self) -> bool:
        """Return whether protected routes require an API key at runtime."""

        return bool(self.api_key)

    @property
    def is_production(self) -> bool:
        return self.runtime_env == "production"

    @classmethod
    def from_env(cls) -> ApiSettings:
        runtime_env = _parse_runtime_env()
        production = runtime_env == "production"
        auth_required = _parse_bool_env(
            "COUNTRY_COMPARE_API_AUTH_REQUIRED",
            default=production,
        )
        enable_docs = _parse_bool_env(
            "COUNTRY_COMPARE_API_ENABLE_DOCS",
            default=not production,
        )
        protect_docs = _parse_bool_env(
            "COUNTRY_COMPARE_API_PROTECT_DOCS",
            default=production,
        )
        enable_metrics = _parse_bool_env(
            "COUNTRY_COMPARE_API_ENABLE_METRICS",
            default=False,
        )
        protect_metrics = _parse_bool_env(
            "COUNTRY_COMPARE_API_PROTECT_METRICS",
            default=production,
        )

        return cls(
            runtime_env=runtime_env,
            cors_origins=_parse_csv_env(
                "COUNTRY_COMPARE_API_CORS_ORIGINS",
                default=cls.cors_origins,
            ),
            max_records=_parse_int_env(
                "COUNTRY_COMPARE_API_MAX_RECORDS", default=500, max_value=10_000
            ),
            max_countries=_parse_int_env(
                "COUNTRY_COMPARE_API_MAX_COUNTRIES", default=50, max_value=250
            ),
            max_metrics=_parse_int_env(
                "COUNTRY_COMPARE_API_MAX_METRICS", default=50, max_value=500
            ),
            max_horizon_years=_parse_int_env(
                "COUNTRY_COMPARE_API_MAX_HORIZON_YEARS",
                default=10,
                max_value=50,
            ),
            max_holdout_years=_parse_int_env(
                "COUNTRY_COMPARE_API_MAX_HOLDOUT_YEARS",
                default=10,
                max_value=50,
            ),
            max_top_n=_parse_int_env(
                "COUNTRY_COMPARE_API_MAX_TOP_N", default=100, max_value=500
            ),
            enable_docs=enable_docs,
            protect_docs=protect_docs,
            enable_metrics=enable_metrics,
            protect_metrics=protect_metrics,
            api_key=_parse_optional_env("COUNTRY_COMPARE_API_KEY"),
            auth_required=auth_required,
            protected_prefixes=_parse_csv_env(
                "COUNTRY_COMPARE_API_PROTECTED_PREFIXES",
                default=cls.protected_prefixes,
            ),
            public_paths=_parse_csv_env(
                "COUNTRY_COMPARE_API_PUBLIC_PATHS",
                default=cls.public_paths,
            ),
            log_level=_parse_optional_env("COUNTRY_COMPARE_API_LOG_LEVEL") or "INFO",
            configure_logging=_parse_bool_env(
                "COUNTRY_COMPARE_API_CONFIGURE_LOGGING",
                default=True,
            ),
            log_format=_parse_optional_env("COUNTRY_COMPARE_API_LOG_FORMAT") or "json",
            log_propagate=_parse_bool_env(
                "COUNTRY_COMPARE_API_LOG_PROPAGATE",
                default=True,
            ),
            log_clear_handlers=_parse_bool_env(
                "COUNTRY_COMPARE_API_LOG_CLEAR_HANDLERS",
                default=False,
            ),
        )


def _parse_runtime_env() -> RuntimeEnv:
    raw_value = _parse_optional_env("COUNTRY_COMPARE_API_ENV")
    raw_value = raw_value or _parse_optional_env("COUNTRY_COMPARE_ENV")
    return (raw_value or "development").lower()


def _parse_optional_env(name: str) -> str | None:
    value = os.getenv(name)
    if value is None:
        return None
    stripped = value.strip()
    return stripped or None


def _parse_csv_env(name: str, *, default: tuple[str, ...]) -> tuple[str, ...]:
    raw_value = os.environ.get(name)
    if raw_value is None:
        return default
    return tuple(value.strip() for value in raw_value.split(",") if value.strip())


def _parse_int_env(name: str, *, default: int, max_value: int) -> int:
    raw_value = os.environ.get(name)
    if raw_value is None or not raw_value.strip():
        return default

    try:
        value = int(raw_value)
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer.") from exc

    if value <= 0:
        raise ValueError(f"{name} must be greater than zero.")
    if value > max_value:
        raise ValueError(f"{name} must be less than or equal to {max_value}.")
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
