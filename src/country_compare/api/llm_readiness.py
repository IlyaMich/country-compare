from __future__ import annotations

import hashlib
import logging
import os
import time
from dataclasses import dataclass
from threading import Lock
from typing import Any, TypedDict

from country_compare.api.schemas.health import LLMReadyResponse
from country_compare.prediction.llm.forecasters import (
    LLMForecastSettings,
    load_llm_forecast_settings,
)
from country_compare.prediction.llm.remote_client import (
    RemoteLLMForecastClient,
    RemoteLLMForecastError,
)

LOGGER = logging.getLogger(__name__)

ENV_LLM_READY_CACHE_TTL_SECONDS = "COUNTRY_COMPARE_LLM_READY_CACHE_TTL_SECONDS"
ENV_LLM_READY_FAILURE_COOLDOWN_SECONDS = (
    "COUNTRY_COMPARE_LLM_READY_FAILURE_COOLDOWN_SECONDS"
)
ENV_LLM_READY_FAILURE_THRESHOLD = "COUNTRY_COMPARE_LLM_READY_FAILURE_THRESHOLD"

DEFAULT_LLM_READY_CACHE_TTL_SECONDS = 10.0
DEFAULT_LLM_READY_FAILURE_COOLDOWN_SECONDS = 30.0
DEFAULT_LLM_READY_FAILURE_THRESHOLD = 3


class _LLMReadyBasePayload(TypedDict):
    enabled: bool
    service_url_configured: bool
    service_token_configured: bool
    provider: str
    model: str


_CacheKey = tuple[object, ...]


@dataclass(frozen=True, slots=True)
class _ReadinessRuntimeSettings:
    cache_ttl_seconds: float
    failure_cooldown_seconds: float
    failure_threshold: int


@dataclass(slots=True)
class _LLMReadyCacheEntry:
    key: _CacheKey
    expires_at: float
    payload: LLMReadyResponse


@dataclass(slots=True)
class _LLMReadyCircuitState:
    consecutive_failures: int = 0
    opened_until: float = 0.0


_CACHE_ENTRY: _LLMReadyCacheEntry | None = None
_CIRCUIT_STATE = _LLMReadyCircuitState()
_STATE_LOCK = Lock()


def build_llm_ready_response() -> LLMReadyResponse:
    """Return cached/circuit-broken backend-to-LLM-service readiness.

    Remote failures are intentionally sanitized in the public response. Full
    exception details are emitted only to logs so the readiness endpoint cannot
    disclose upstream hostnames, provider messages, traces, or token-adjacent
    diagnostics.
    """

    settings = load_llm_forecast_settings()
    runtime_settings = _readiness_runtime_settings()
    now = time.monotonic()
    key = _cache_key(settings, runtime_settings)

    cached_payload = _get_cached_payload(key, now)
    if cached_payload is not None:
        return cached_payload

    base_payload: _LLMReadyBasePayload = {
        "enabled": settings.enabled,
        "service_url_configured": bool(settings.service_url),
        "service_token_configured": bool(settings.service_token),
        "provider": settings.provider,
        "model": settings.model,
    }

    config_warnings = _llm_config_warnings(
        enabled=settings.enabled,
        service_url=settings.service_url,
        service_token=settings.service_token,
    )
    if config_warnings:
        payload = LLMReadyResponse(
            status="not_ready",
            **base_payload,
            warnings=config_warnings,
        )
        _set_cached_payload(key, now, runtime_settings.cache_ttl_seconds, payload)
        return payload

    cooldown_payload = _cooldown_payload_if_open(
        key=key,
        now=now,
        ttl_seconds=runtime_settings.cache_ttl_seconds,
        base_payload=base_payload,
    )
    if cooldown_payload is not None:
        return cooldown_payload

    client = RemoteLLMForecastClient(
        service_url=settings.service_url,
        service_token=settings.service_token,
        timeout_seconds=min(settings.service_timeout_seconds, 5.0),
        max_adjustment_pct=settings.max_adjustment_pct,
    )

    try:
        capabilities = client.capabilities()
    except RemoteLLMForecastError as exc:
        payload = _remote_failure_payload(
            base_payload=base_payload,
            warning="Backend could not reach a ready LLM forecast service.",
        )
        _record_remote_failure(
            key=key,
            now=now,
            runtime_settings=runtime_settings,
            payload=payload,
            exc=exc,
            exc_type="remote_llm_forecast_error",
        )
        return payload
    except Exception as exc:
        payload = _remote_failure_payload(
            base_payload=base_payload,
            warning="Backend LLM readiness check failed unexpectedly.",
        )
        _record_remote_failure(
            key=key,
            now=now,
            runtime_settings=runtime_settings,
            payload=payload,
            exc=exc,
            exc_type="unexpected_error",
        )
        return payload

    capability_warnings = _llm_capability_warnings(capabilities)
    payload = LLMReadyResponse(
        status="ready" if not capability_warnings else "not_ready",
        **base_payload,
        capabilities={str(key): value for key, value in capabilities.items()},
        warnings=capability_warnings,
    )
    _record_remote_success(key, now, runtime_settings.cache_ttl_seconds, payload)
    return payload


def reset_llm_readiness_state_for_tests() -> None:
    global _CACHE_ENTRY
    with _STATE_LOCK:
        _CACHE_ENTRY = None
        _CIRCUIT_STATE.consecutive_failures = 0
        _CIRCUIT_STATE.opened_until = 0.0


def _readiness_runtime_settings() -> _ReadinessRuntimeSettings:
    return _ReadinessRuntimeSettings(
        cache_ttl_seconds=_env_float(
            ENV_LLM_READY_CACHE_TTL_SECONDS,
            DEFAULT_LLM_READY_CACHE_TTL_SECONDS,
            min_value=0.0,
        ),
        failure_cooldown_seconds=_env_float(
            ENV_LLM_READY_FAILURE_COOLDOWN_SECONDS,
            DEFAULT_LLM_READY_FAILURE_COOLDOWN_SECONDS,
            min_value=0.0,
        ),
        failure_threshold=_env_int(
            ENV_LLM_READY_FAILURE_THRESHOLD,
            DEFAULT_LLM_READY_FAILURE_THRESHOLD,
            min_value=1,
        ),
    )


def _env_float(name: str, default: float, *, min_value: float) -> float:
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default
    try:
        value = float(raw)
    except ValueError:
        LOGGER.warning(
            "llm_readiness.invalid_float_env",
            extra={"env_name": name, "default": default},
        )
        return default
    return max(min_value, value)


def _env_int(name: str, default: int, *, min_value: int) -> int:
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default
    try:
        value = int(raw)
    except ValueError:
        LOGGER.warning(
            "llm_readiness.invalid_int_env",
            extra={"env_name": name, "default": default},
        )
        return default
    return max(min_value, value)


def _cache_key(
    settings: LLMForecastSettings,
    runtime_settings: _ReadinessRuntimeSettings,
) -> _CacheKey:
    token_fingerprint = (
        hashlib.sha256(settings.service_token.encode("utf-8")).hexdigest()
        if settings.service_token
        else ""
    )
    return (
        settings.enabled,
        settings.provider,
        settings.model,
        settings.service_url,
        token_fingerprint,
        settings.service_timeout_seconds,
        settings.max_adjustment_pct,
        runtime_settings.cache_ttl_seconds,
        runtime_settings.failure_cooldown_seconds,
        runtime_settings.failure_threshold,
    )


def _get_cached_payload(key: _CacheKey, now: float) -> LLMReadyResponse | None:
    with _STATE_LOCK:
        if _CACHE_ENTRY is None:
            return None
        if _CACHE_ENTRY.key != key or _CACHE_ENTRY.expires_at <= now:
            return None
        return _clone_payload(_CACHE_ENTRY.payload)


def _set_cached_payload(
    key: _CacheKey,
    now: float,
    ttl_seconds: float,
    payload: LLMReadyResponse,
) -> None:
    global _CACHE_ENTRY
    with _STATE_LOCK:
        _CACHE_ENTRY = _LLMReadyCacheEntry(
            key=key,
            expires_at=now + ttl_seconds,
            payload=_clone_payload(payload),
        )


def _cooldown_payload_if_open(
    *,
    key: _CacheKey,
    now: float,
    ttl_seconds: float,
    base_payload: _LLMReadyBasePayload,
) -> LLMReadyResponse | None:
    with _STATE_LOCK:
        opened_until = _CIRCUIT_STATE.opened_until

    if opened_until <= now:
        return None

    payload = LLMReadyResponse(
        status="not_ready",
        **base_payload,
        warnings=[
            "Backend LLM readiness checks are temporarily paused after repeated failures."
        ],
        error="LLM readiness check is temporarily unavailable; retry later.",
    )
    _set_cached_payload(key, now, ttl_seconds, payload)
    return payload


def _record_remote_failure(
    *,
    key: _CacheKey,
    now: float,
    runtime_settings: _ReadinessRuntimeSettings,
    payload: LLMReadyResponse,
    exc: Exception,
    exc_type: str,
) -> None:
    global _CACHE_ENTRY

    LOGGER.warning(
        "llm_readiness.remote_check_failed",
        extra={"error_type": exc_type, "error": str(exc)},
        exc_info=True,
    )

    with _STATE_LOCK:
        _CIRCUIT_STATE.consecutive_failures += 1
        if _CIRCUIT_STATE.consecutive_failures >= runtime_settings.failure_threshold:
            _CIRCUIT_STATE.opened_until = (
                now + runtime_settings.failure_cooldown_seconds
            )

        _CACHE_ENTRY = _LLMReadyCacheEntry(
            key=key,
            expires_at=now + runtime_settings.cache_ttl_seconds,
            payload=_clone_payload(payload),
        )


def _record_remote_success(
    key: _CacheKey,
    now: float,
    ttl_seconds: float,
    payload: LLMReadyResponse,
) -> None:
    with _STATE_LOCK:
        _CIRCUIT_STATE.consecutive_failures = 0
        _CIRCUIT_STATE.opened_until = 0.0

    _set_cached_payload(key, now, ttl_seconds, payload)


def _remote_failure_payload(
    *,
    base_payload: _LLMReadyBasePayload,
    warning: str,
) -> LLMReadyResponse:
    return LLMReadyResponse(
        status="not_ready",
        **base_payload,
        warnings=[warning],
        error="LLM readiness check failed.",
    )


def _llm_config_warnings(
    *,
    enabled: bool,
    service_url: str,
    service_token: str,
) -> list[str]:
    warnings: list[str] = []
    if not enabled:
        warnings.append("LLM forecasting is disabled.")
    if not service_url:
        warnings.append("LLM forecast service URL is not configured.")
    if not service_token:
        warnings.append("LLM forecast service token is not configured.")
    return warnings


def _llm_capability_warnings(capabilities: dict[str, Any]) -> list[str]:
    warnings: list[str] = []

    if not bool(capabilities.get("supports_structured_output")):
        warnings.append("LLM service does not report structured output support.")

    if not bool(capabilities.get("supports_bounded_adjustment")):
        warnings.append("LLM service does not report bounded adjustment support.")

    max_series_per_request = _optional_int(capabilities.get("max_series_per_request"))
    if max_series_per_request is None or max_series_per_request < 1:
        warnings.append("LLM service max_series_per_request is invalid.")

    max_horizon_years = _optional_int(capabilities.get("max_horizon_years"))
    if max_horizon_years is None or max_horizon_years < 1:
        warnings.append("LLM service max_horizon_years is invalid.")

    return warnings


def _optional_int(value: object) -> int | None:
    if value is None:
        return None

    # bool is a subclass of int, but should not be accepted as a numeric limit.
    if isinstance(value, bool):
        return None

    if isinstance(value, int):
        return value

    if isinstance(value, float):
        if value.is_integer():
            return int(value)
        return None

    if isinstance(value, str):
        raw_value = value.strip()
        if not raw_value:
            return None
        try:
            return int(raw_value)
        except ValueError:
            return None

    return None


def _clone_payload(payload: LLMReadyResponse) -> LLMReadyResponse:
    return payload.model_copy(deep=True)
