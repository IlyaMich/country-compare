from __future__ import annotations

import os
from dataclasses import dataclass

from llm_forecast_service.metrics import (
    DEFAULT_FORECAST_DURATION_BUCKETS,
    DEFAULT_HTTP_DURATION_BUCKETS,
    DEFAULT_PROVIDER_DURATION_BUCKETS,
    DEFAULT_QUEUE_WAIT_BUCKETS,
)

VALID_DEPLOYMENT_PROFILES = frozenset({"local", "public"})
VALID_PROVIDERS = frozenset({"mistral", "baseline_echo"})
_BOOL_TRUE = frozenset({"1", "true", "yes", "y", "on"})
_BOOL_FALSE = frozenset({"0", "false", "no", "n", "off"})


class SettingsError(ValueError):
    """Raised when environment-driven service settings are invalid."""


def _get_optional_env(name: str) -> str | None:
    raw = os.getenv(name)
    if raw is None:
        return None
    value = raw.strip()
    return value or None


def _get_bool(name: str, default: bool) -> bool:
    raw = _get_optional_env(name)
    if raw is None:
        return default
    value = raw.lower()
    if value in _BOOL_TRUE:
        return True
    if value in _BOOL_FALSE:
        return False
    raise SettingsError(
        f"{name} must be a boolean value: one of "
        "1/0, true/false, yes/no, y/n, on/off."
    )


def _get_int(name: str, default: int, *, min_value: int | None = None) -> int:
    raw = _get_optional_env(name)
    if raw is None:
        value = default
    else:
        try:
            value = int(raw)
        except ValueError as exc:
            raise SettingsError(f"{name} must be an integer.") from exc
    if min_value is not None and value < min_value:
        raise SettingsError(f"{name} must be >= {min_value}.")
    return value


def _get_float(name: str, default: float, *, min_value: float | None = None) -> float:
    raw = _get_optional_env(name)
    if raw is None:
        value = default
    else:
        try:
            value = float(raw)
        except ValueError as exc:
            raise SettingsError(f"{name} must be a number.") from exc
    if min_value is not None and value < min_value:
        raise SettingsError(f"{name} must be >= {min_value}.")
    return value


def _get_float_tuple(
    name: str,
    default: tuple[float, ...],
    *,
    min_value: float = 0.0,
) -> tuple[float, ...]:
    raw = _get_optional_env(name)
    if raw is None:
        values = default
    else:
        parts = [part.strip() for part in raw.split(",") if part.strip()]
        if not parts:
            raise SettingsError(
                f"{name} must contain at least one comma-separated number."
            )
        try:
            values = tuple(float(part) for part in parts)
        except ValueError as exc:
            raise SettingsError(
                f"{name} must be a comma-separated list of numbers."
            ) from exc

    previous: float | None = None
    for value in values:
        if value <= min_value:
            raise SettingsError(f"{name} values must be > {min_value}.")
        if previous is not None and value <= previous:
            raise SettingsError(f"{name} values must be strictly increasing.")
        previous = value

    return values


@dataclass(frozen=True)
class ServiceSettings:
    service_token: str = ""
    provider: str = "mistral"
    mistral_api_key: str = ""
    mistral_model: str = "mistral-large-latest"
    deployment_profile: str = "local"
    require_zdr: bool = False
    mistral_zdr_confirmed: bool = False
    timeout_seconds: float = 20.0
    queue_timeout_seconds: float = 2.0
    max_retries: int = 1
    max_concurrent_requests: int = 1
    temperature: float = 0.0
    max_output_tokens: int = 800
    max_series_per_request: int = 3
    max_horizon_years: int = 10
    max_history_points: int = 80
    max_input_chars: int = 12_000
    max_adjustment_pct: float = 15.0
    max_warnings: int = 5
    max_assumptions: int = 5
    max_warning_length: int = 500
    max_assumption_length: int = 500
    log_level: str = "INFO"
    debug_log_payloads: bool = False
    enable_metrics: bool = True
    protect_metrics: bool = True
    protect_ready_details: bool = True
    enable_docs: bool = True
    http_duration_buckets: tuple[float, ...] = DEFAULT_HTTP_DURATION_BUCKETS
    forecast_duration_buckets: tuple[float, ...] = DEFAULT_FORECAST_DURATION_BUCKETS
    provider_duration_buckets: tuple[float, ...] = DEFAULT_PROVIDER_DURATION_BUCKETS
    queue_wait_buckets: tuple[float, ...] = DEFAULT_QUEUE_WAIT_BUCKETS

    @classmethod
    def from_env(cls) -> ServiceSettings:
        deployment_profile = (
            _get_optional_env("LLM_DEPLOYMENT_PROFILE") or "local"
        ).lower()
        provider = (_get_optional_env("LLM_PROVIDER") or "mistral").lower()
        log_level = (_get_optional_env("LLM_LOG_LEVEL") or "INFO").upper()
        debug_log_payloads = _get_bool("LLM_DEBUG_LOG_PAYLOADS", False)
        if deployment_profile == "public":
            debug_log_payloads = False

        settings = cls(
            service_token=_get_optional_env("LLM_SERVICE_TOKEN") or "",
            provider=provider,
            mistral_api_key=_get_optional_env("MISTRAL_API_KEY") or "",
            mistral_model=_get_optional_env("MISTRAL_MODEL") or "mistral-large-latest",
            deployment_profile=deployment_profile,
            require_zdr=_get_bool("LLM_REQUIRE_ZDR", False),
            mistral_zdr_confirmed=_get_bool("MISTRAL_ZDR_CONFIRMED", False),
            timeout_seconds=_get_float("LLM_TIMEOUT_SECONDS", 20.0, min_value=0.001),
            queue_timeout_seconds=_get_float(
                "LLM_QUEUE_TIMEOUT_SECONDS", 2.0, min_value=0.001
            ),
            max_retries=_get_int("LLM_MAX_RETRIES", 1, min_value=0),
            max_concurrent_requests=_get_int(
                "LLM_MAX_CONCURRENT_REQUESTS", 1, min_value=1
            ),
            temperature=_get_float("LLM_TEMPERATURE", 0.0, min_value=0.0),
            max_output_tokens=_get_int("LLM_MAX_OUTPUT_TOKENS", 800, min_value=1),
            max_series_per_request=_get_int(
                "LLM_MAX_SERIES_PER_REQUEST", 3, min_value=1
            ),
            max_horizon_years=_get_int("LLM_MAX_HORIZON_YEARS", 10, min_value=1),
            max_history_points=_get_int("LLM_MAX_HISTORY_POINTS", 80, min_value=1),
            max_input_chars=_get_int("LLM_MAX_INPUT_CHARS", 12_000, min_value=1),
            max_adjustment_pct=_get_float(
                "LLM_MAX_ADJUSTMENT_PCT", 15.0, min_value=0.001
            ),
            max_warnings=_get_int("LLM_MAX_WARNINGS", 5, min_value=0),
            max_assumptions=_get_int("LLM_MAX_ASSUMPTIONS", 5, min_value=0),
            max_warning_length=_get_int("LLM_MAX_WARNING_LENGTH", 500, min_value=1),
            max_assumption_length=_get_int(
                "LLM_MAX_ASSUMPTION_LENGTH", 500, min_value=1
            ),
            log_level=log_level,
            debug_log_payloads=debug_log_payloads,
            enable_metrics=_get_bool("LLM_ENABLE_METRICS", True),
            protect_metrics=_get_bool("LLM_PROTECT_METRICS", True),
            protect_ready_details=_get_bool("LLM_PROTECT_READY_DETAILS", True),
            enable_docs=_get_bool("LLM_ENABLE_DOCS", True),
            http_duration_buckets=_get_float_tuple(
                "LLM_HTTP_DURATION_BUCKETS",
                DEFAULT_HTTP_DURATION_BUCKETS,
            ),
            forecast_duration_buckets=_get_float_tuple(
                "LLM_FORECAST_DURATION_BUCKETS",
                DEFAULT_FORECAST_DURATION_BUCKETS,
            ),
            provider_duration_buckets=_get_float_tuple(
                "LLM_PROVIDER_DURATION_BUCKETS",
                DEFAULT_PROVIDER_DURATION_BUCKETS,
            ),
            queue_wait_buckets=_get_float_tuple(
                "LLM_QUEUE_WAIT_BUCKETS",
                DEFAULT_QUEUE_WAIT_BUCKETS,
            ),
        )
        issues = settings.readiness_issues(include_runtime_dependencies=False)
        if issues:
            raise SettingsError("; ".join(issues))
        return settings

    def readiness_issues(
        self, *, include_runtime_dependencies: bool = True
    ) -> list[str]:
        issues: list[str] = []
        if self.provider not in VALID_PROVIDERS:
            issues.append(f"Unsupported LLM_PROVIDER: {self.provider}")
        if self.deployment_profile not in VALID_DEPLOYMENT_PROFILES:
            issues.append(
                f"Unsupported LLM_DEPLOYMENT_PROFILE: {self.deployment_profile}"
            )
        if self.max_concurrent_requests < 1:
            issues.append("LLM_MAX_CONCURRENT_REQUESTS must be at least 1")
        if self.queue_timeout_seconds <= 0:
            issues.append("LLM_QUEUE_TIMEOUT_SECONDS must be greater than 0")
        if self.timeout_seconds <= 0:
            issues.append("LLM_TIMEOUT_SECONDS must be greater than 0")
        if self.max_retries < 0:
            issues.append("LLM_MAX_RETRIES must be at least 0")
        if self.max_output_tokens < 1:
            issues.append("LLM_MAX_OUTPUT_TOKENS must be at least 1")
        if self.max_horizon_years < 1:
            issues.append("LLM_MAX_HORIZON_YEARS must be at least 1")
        if self.max_history_points < 1:
            issues.append("LLM_MAX_HISTORY_POINTS must be at least 1")
        if self.max_input_chars < 1:
            issues.append("LLM_MAX_INPUT_CHARS must be at least 1")
        if self.max_adjustment_pct <= 0:
            issues.append("LLM_MAX_ADJUSTMENT_PCT must be greater than 0")
        for setting_name in (
            "http_duration_buckets",
            "forecast_duration_buckets",
            "provider_duration_buckets",
            "queue_wait_buckets",
        ):
            _validate_bucket_tuple(setting_name, getattr(self, setting_name), issues)
        if include_runtime_dependencies and not self.service_token:
            issues.append("LLM_SERVICE_TOKEN is not configured")
        if self.provider == "mistral":
            if include_runtime_dependencies and not self.mistral_api_key:
                issues.append("MISTRAL_API_KEY is not configured")
            if not self.mistral_model:
                issues.append("MISTRAL_MODEL is not configured")
        if self.is_public_deployment:
            if self.provider == "baseline_echo":
                issues.append(
                    "baseline_echo provider is not allowed for public deployments"
                )
            if include_runtime_dependencies and not self.service_token:
                issues.append("LLM_SERVICE_TOKEN is not configured")
            if not self.require_zdr:
                issues.append("LLM_REQUIRE_ZDR must be true for public deployments")
            if not self.mistral_zdr_confirmed:
                issues.append(
                    "MISTRAL_ZDR_CONFIRMED must be true for public deployments"
                )
        return issues

    @property
    def is_ready(self) -> bool:
        return not self.readiness_issues()

    @property
    def is_public_deployment(self) -> bool:
        return self.deployment_profile == "public"

    @property
    def effective_debug_log_payloads(self) -> bool:
        return bool(self.debug_log_payloads and not self.is_public_deployment)

    @property
    def effective_enable_docs(self) -> bool:
        """Return whether interactive docs/OpenAPI should be exposed."""

        if self.deployment_profile == "public":
            return False

        return self.enable_docs


def _validate_bucket_tuple(
    name: str,
    values: tuple[float, ...],
    issues: list[str],
) -> None:
    if not values:
        issues.append(f"{name} must contain at least one bucket")
        return

    previous: float | None = None
    for value in values:
        if value <= 0:
            issues.append(f"{name} values must be greater than 0")
        if previous is not None and value <= previous:
            issues.append(f"{name} values must be strictly increasing")
        previous = value
