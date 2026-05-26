from __future__ import annotations

import math
import os
from dataclasses import dataclass, field

import pandas as pd

from country_compare.data.contract import VALUE_COLUMN, YEAR_COLUMN
from country_compare.prediction.errors import PredictionErrorCode, PredictionException
from country_compare.prediction.forecasters import BaseForecaster
from country_compare.prediction.llm.client import (
    DisabledLLMForecastClient,
    LLMForecastAvailabilityClient,
    LLMForecastClient,
    LLMForecastRequest,
    LLMForecastResponse,
)
from country_compare.prediction.llm.prompts import LLM_FORECAST_PROMPT_VERSION
from country_compare.prediction.models import (
    ForecastContext,
    ForecastOptions,
    ForecastPoint,
    RawForecastResult,
)
from country_compare.settings.defaults import (
    DEFAULT_ENABLE_LLM_FORECAST,
    DEFAULT_LLM_BASELINE_METHOD,
    DEFAULT_LLM_MAX_ADJUSTMENT_PCT,
    DEFAULT_LLM_MAX_HISTORY_POINTS,
    DEFAULT_LLM_MAX_RETRIES,
    DEFAULT_LLM_MAX_SERIES_PER_REQUEST,
    DEFAULT_LLM_MODEL,
    DEFAULT_LLM_PROVIDER,
    DEFAULT_LLM_SERVICE_TIMEOUT_SECONDS,
    DEFAULT_LLM_SERVICE_TOKEN,
    DEFAULT_LLM_SERVICE_URL,
    DEFAULT_LLM_TIMEOUT_SECONDS,
)

ENV_ENABLE_LLM_FORECAST = "COUNTRY_COMPARE_ENABLE_LLM_FORECAST"
ENV_LLM_PROVIDER = "COUNTRY_COMPARE_LLM_PROVIDER"
ENV_LLM_MODEL = "COUNTRY_COMPARE_LLM_MODEL"
ENV_LLM_TIMEOUT_SECONDS = "COUNTRY_COMPARE_LLM_TIMEOUT_SECONDS"
ENV_LLM_MAX_RETRIES = "COUNTRY_COMPARE_LLM_MAX_RETRIES"
ENV_LLM_BASELINE_METHOD = "COUNTRY_COMPARE_LLM_BASELINE_METHOD"
ENV_LLM_MAX_HISTORY_POINTS = "COUNTRY_COMPARE_LLM_MAX_HISTORY_POINTS"
ENV_LLM_MAX_ADJUSTMENT_PCT = "COUNTRY_COMPARE_LLM_MAX_ADJUSTMENT_PCT"
ENV_LLM_SERVICE_URL = "COUNTRY_COMPARE_LLM_SERVICE_URL"
ENV_LLM_SERVICE_TOKEN = "COUNTRY_COMPARE_LLM_SERVICE_TOKEN"
ENV_LLM_SERVICE_TIMEOUT_SECONDS = "COUNTRY_COMPARE_LLM_SERVICE_TIMEOUT_SECONDS"
ENV_LLM_MAX_SERIES_PER_REQUEST = "COUNTRY_COMPARE_LLM_MAX_SERIES_PER_REQUEST"


@dataclass(frozen=True, slots=True)
class LLMForecastSettings:
    enabled: bool = DEFAULT_ENABLE_LLM_FORECAST
    provider: str = DEFAULT_LLM_PROVIDER
    model: str = DEFAULT_LLM_MODEL
    timeout_seconds: int = DEFAULT_LLM_TIMEOUT_SECONDS
    max_retries: int = DEFAULT_LLM_MAX_RETRIES
    baseline_method: str = DEFAULT_LLM_BASELINE_METHOD
    max_history_points: int = DEFAULT_LLM_MAX_HISTORY_POINTS
    max_adjustment_pct: float = DEFAULT_LLM_MAX_ADJUSTMENT_PCT
    service_url: str = DEFAULT_LLM_SERVICE_URL
    service_token: str = field(default=DEFAULT_LLM_SERVICE_TOKEN, repr=False)
    service_timeout_seconds: float = DEFAULT_LLM_SERVICE_TIMEOUT_SECONDS
    max_series_per_request: int = DEFAULT_LLM_MAX_SERIES_PER_REQUEST


_CLIENT_OVERRIDE: LLMForecastClient | None = None


def set_llm_forecast_client_override(client: LLMForecastClient | None) -> None:
    """Override the configured LLM client.

    This is primarily intended for tests and local experiments. A real provider
    adapter can later call into the same interface without changing forecaster
    behavior.
    """

    global _CLIENT_OVERRIDE
    _CLIENT_OVERRIDE = client


def load_llm_forecast_settings() -> LLMForecastSettings:
    return LLMForecastSettings(
        enabled=_env_bool(ENV_ENABLE_LLM_FORECAST, DEFAULT_ENABLE_LLM_FORECAST),
        provider=_env_text(ENV_LLM_PROVIDER, DEFAULT_LLM_PROVIDER),
        model=_env_text(ENV_LLM_MODEL, DEFAULT_LLM_MODEL),
        timeout_seconds=_env_int(ENV_LLM_TIMEOUT_SECONDS, DEFAULT_LLM_TIMEOUT_SECONDS),
        max_retries=_env_int(ENV_LLM_MAX_RETRIES, DEFAULT_LLM_MAX_RETRIES),
        baseline_method=_env_text(ENV_LLM_BASELINE_METHOD, DEFAULT_LLM_BASELINE_METHOD),
        max_history_points=max(
            1,
            _env_int(
                ENV_LLM_MAX_HISTORY_POINTS,
                DEFAULT_LLM_MAX_HISTORY_POINTS,
            ),
        ),
        max_adjustment_pct=max(
            0.0,
            _env_float(
                ENV_LLM_MAX_ADJUSTMENT_PCT,
                DEFAULT_LLM_MAX_ADJUSTMENT_PCT,
            ),
        ),
        service_url=_env_text(ENV_LLM_SERVICE_URL, DEFAULT_LLM_SERVICE_URL),
        service_token=_env_text(ENV_LLM_SERVICE_TOKEN, DEFAULT_LLM_SERVICE_TOKEN),
        service_timeout_seconds=max(
            0.1,
            _env_float(
                ENV_LLM_SERVICE_TIMEOUT_SECONDS,
                DEFAULT_LLM_SERVICE_TIMEOUT_SECONDS,
            ),
        ),
        max_series_per_request=max(
            1,
            _env_int(
                ENV_LLM_MAX_SERIES_PER_REQUEST,
                DEFAULT_LLM_MAX_SERIES_PER_REQUEST,
            ),
        ),
    )


def get_configured_llm_forecast_client() -> LLMForecastClient:
    if _CLIENT_OVERRIDE is not None:
        return _CLIENT_OVERRIDE

    settings = load_llm_forecast_settings()
    if not _has_remote_service_config(settings):
        return DisabledLLMForecastClient()

    return _remote_client_from_settings(settings)


def is_llm_forecast_available() -> bool:
    settings = load_llm_forecast_settings()
    if not settings.enabled:
        return False

    if _CLIENT_OVERRIDE is not None:
        return True

    if not _has_remote_service_config(settings):
        return False

    client = _remote_client_from_settings(
        settings,
        timeout_seconds=min(settings.service_timeout_seconds, 3.0),
    )
    if isinstance(client, DisabledLLMForecastClient):
        return False

    if not isinstance(client, LLMForecastAvailabilityClient):
        return False

    try:
        return bool(client.is_available())
    except Exception:
        return False


class LLMForecastForecaster(BaseForecaster):
    method_id = "llm_forecast"
    display_name = "LLM forecast — experimental"
    description = (
        "Uses a configured LLM client to adjust a deterministic baseline forecast "
        "with strict validation and safe fallback."
    )

    minimum_observations = 1

    def __init__(
        self,
        *,
        client: LLMForecastClient | None = None,
        settings: LLMForecastSettings | None = None,
    ) -> None:
        self._client = client
        self._settings = settings

    def supports(
        self,
        series: pd.DataFrame,
        *,
        context: ForecastContext,
        options: ForecastOptions,
    ) -> tuple[bool, list[str]]:
        settings = self._resolved_settings()
        reasons: list[str] = []

        if not settings.enabled:
            reasons.append(
                f"llm_forecast is disabled; set {ENV_ENABLE_LLM_FORECAST}=true "
                "to enable it"
            )

        if isinstance(self._resolved_client(), DisabledLLMForecastClient):
            reasons.append("llm_forecast has no configured LLM client")

        years = pd.to_numeric(series[YEAR_COLUMN], errors="coerce").dropna()
        values = pd.to_numeric(series[VALUE_COLUMN], errors="coerce").dropna()

        if len(series.index) < self.minimum_observations:
            reasons.append("llm_forecast requires at least one observation")

        if len(years.index) < len(series.index):
            reasons.append("llm_forecast requires numeric years for every observation")

        if len(values.index) < len(series.index):
            reasons.append("llm_forecast requires numeric values for every observation")

        _, baseline_reasons = self._select_baseline_forecaster(
            series,
            context=context,
            options=options,
            settings=settings,
        )
        reasons.extend(baseline_reasons)

        return len(reasons) == 0, reasons

    def forecast(
        self,
        series: pd.DataFrame,
        future_years: list[int],
        *,
        context: ForecastContext,
        options: ForecastOptions,
    ) -> RawForecastResult:
        self._require_supported(series, context=context, options=options)

        settings = self._resolved_settings()
        client = self._resolved_client()
        baseline_result, baseline_method = self._forecast_baseline(
            series,
            future_years,
            context=context,
            options=options,
            settings=settings,
        )

        llm_request = LLMForecastRequest(
            country_code=context.country_code,
            country_name=context.country_name,
            metric_id=context.metric_id,
            metric_name=context.metric_name,
            unit=context.unit,
            history=self._history_payload(series, settings=settings),
            baseline_forecast=[
                {"year": point.year, "value": point.value}
                for point in baseline_result.points
            ],
            horizon_years=len(future_years),
            prompt_version=LLM_FORECAST_PROMPT_VERSION,
        )

        try:
            llm_response = client.forecast(llm_request)
            validated_points = _validate_llm_response(
                llm_response,
                future_years=future_years,
                baseline_points=baseline_result.points,
                max_adjustment_pct=settings.max_adjustment_pct,
            )
        except Exception as exc:
            return self._fallback_result(
                baseline_result,
                settings=settings,
                baseline_method=baseline_method,
                failure_reason=str(exc),
            )

        metadata = self._metadata(
            settings=settings,
            baseline_method=baseline_method,
            llm_called=True,
            validation_status="valid",
            fallback_used=False,
            rationale=llm_response.rationale,
            assumptions=llm_response.assumptions,
            risk_warnings=llm_response.warnings,
            raw_provider_metadata=llm_response.raw_provider_metadata,
        )

        warnings = [
            "llm_forecast is experimental and should be treated as an exploratory "
            "scenario, not a guarantee",
            *baseline_result.warnings,
            *llm_response.warnings,
        ]

        return RawForecastResult(
            method_id=self.method_id,
            points=validated_points,
            forecaster_info=self.info(metadata=metadata),
            diagnostics_metadata=metadata,
            warnings=warnings,
        )

    def _resolved_settings(self) -> LLMForecastSettings:
        return self._settings or load_llm_forecast_settings()

    def _resolved_client(self) -> LLMForecastClient:
        return self._client or get_configured_llm_forecast_client()

    def _forecast_baseline(
        self,
        series: pd.DataFrame,
        future_years: list[int],
        *,
        context: ForecastContext,
        options: ForecastOptions,
        settings: LLMForecastSettings,
    ) -> tuple[RawForecastResult, str]:
        forecaster, reasons = self._select_baseline_forecaster(
            series,
            context=context,
            options=options,
            settings=settings,
        )

        if forecaster is None:
            raise PredictionException(
                PredictionErrorCode.INSUFFICIENT_HISTORY,
                "; ".join(reasons) or "no supported llm_forecast baseline method",
                country_code=context.country_code,
                metric_id=context.metric_id,
                details={
                    "method": self.method_id,
                    "baseline_method": settings.baseline_method,
                    "reasons": reasons,
                },
            )

        return (
            forecaster.forecast(
                series,
                future_years,
                context=context,
                options=options,
            ),
            forecaster.method_id,
        )

    def _select_baseline_forecaster(
        self,
        series: pd.DataFrame,
        *,
        context: ForecastContext,
        options: ForecastOptions,
        settings: LLMForecastSettings,
    ) -> tuple[BaseForecaster | None, list[str]]:
        from country_compare.prediction.registry import (
            ForecasterRegistryError,
            resolve_forecaster,
        )

        reasons: list[str] = []

        for method_id in _baseline_method_candidates(settings):
            try:
                forecaster = resolve_forecaster(method_id)
            except ForecasterRegistryError as exc:
                reasons.append(f"baseline method '{method_id}' is unavailable: {exc}")
                continue

            supported, support_reasons = forecaster.supports(
                series,
                context=context,
                options=options,
            )
            if supported:
                return forecaster, []

            reasons.extend(
                f"baseline method '{method_id}' unsupported: {reason}"
                for reason in support_reasons
            )

        return None, reasons

    def _history_payload(
        self,
        series: pd.DataFrame,
        *,
        settings: LLMForecastSettings,
    ) -> list[dict[str, float | int | str | None]]:
        sorted_series = series.copy(deep=True)
        sorted_series[YEAR_COLUMN] = pd.to_numeric(
            sorted_series[YEAR_COLUMN],
            errors="coerce",
        ).astype("int64")
        sorted_series[VALUE_COLUMN] = pd.to_numeric(
            sorted_series[VALUE_COLUMN],
            errors="coerce",
        ).astype("float64")
        sorted_series = sorted_series.sort_values(by=YEAR_COLUMN, kind="mergesort")
        sorted_series = sorted_series.tail(settings.max_history_points)

        return [
            {
                "year": int(row[YEAR_COLUMN]),
                "value": float(row[VALUE_COLUMN]),
            }
            for _, row in sorted_series.iterrows()
        ]

    def _fallback_result(
        self,
        baseline_result: RawForecastResult,
        *,
        settings: LLMForecastSettings,
        baseline_method: str,
        failure_reason: str,
    ) -> RawForecastResult:
        metadata = self._metadata(
            settings=settings,
            baseline_method=baseline_method,
            llm_called=True,
            validation_status="fallback",
            fallback_used=True,
            fallback_method=baseline_method,
            failure_reason=failure_reason,
        )

        warnings = [
            "llm_forecast could not produce a valid forecast; returned the "
            f"validated baseline forecast from '{baseline_method}' instead",
            f"llm_forecast failure reason: {failure_reason}",
            *baseline_result.warnings,
        ]

        return RawForecastResult(
            method_id=self.method_id,
            points=list(baseline_result.points),
            forecaster_info=self.info(metadata=metadata),
            diagnostics_metadata=metadata,
            warnings=warnings,
        )

    def _metadata(
        self,
        *,
        settings: LLMForecastSettings,
        baseline_method: str,
        llm_called: bool,
        validation_status: str,
        fallback_used: bool,
        fallback_method: str | None = None,
        failure_reason: str | None = None,
        rationale: str = "",
        assumptions: list[str] | None = None,
        risk_warnings: list[str] | None = None,
        raw_provider_metadata: dict[str, object] | None = None,
    ) -> dict[str, object]:
        return {
            "method": self.method_id,
            "experimental": True,
            "enabled": settings.enabled,
            "provider": settings.provider,
            "model": settings.model,
            "prompt_version": LLM_FORECAST_PROMPT_VERSION,
            "baseline_method": baseline_method,
            "timeout_seconds": settings.timeout_seconds,
            "max_retries": settings.max_retries,
            "max_history_points": settings.max_history_points,
            "max_adjustment_pct": settings.max_adjustment_pct,
            "llm_called": llm_called,
            "validation_status": validation_status,
            "fallback_used": fallback_used,
            "fallback_method": fallback_method,
            "failure_reason": failure_reason,
            "rationale": rationale,
            "assumptions": list(assumptions or []),
            "risk_warnings": list(risk_warnings or []),
            "raw_provider_metadata": dict(raw_provider_metadata or {}),
        }


def _validate_llm_response(
    response: LLMForecastResponse,
    *,
    future_years: list[int],
    baseline_points: list[ForecastPoint],
    max_adjustment_pct: float,
) -> list[ForecastPoint]:
    if len(response.forecast_points) != len(future_years):
        raise ValueError(
            "LLM response forecast point count did not match requested horizon"
        )

    response_years = [point.year for point in response.forecast_points]
    if response_years != [int(year) for year in future_years]:
        raise ValueError("LLM response years did not match requested forecast years")

    baseline_by_year = {point.year: point.value for point in baseline_points}
    validated_points: list[ForecastPoint] = []
    seen_years: set[int] = set()

    for index, point in enumerate(response.forecast_points):
        if point.year in seen_years:
            raise ValueError(f"LLM response contained duplicate year {point.year}")
        seen_years.add(point.year)

        value = float(point.value)
        if not math.isfinite(value):
            raise ValueError(f"LLM response value for year {point.year} was not finite")

        baseline_value = float(baseline_by_year[point.year])
        allowed_delta = abs(baseline_value) * (max_adjustment_pct / 100.0)
        observed_delta = abs(value - baseline_value)

        if observed_delta > allowed_delta:
            raise ValueError(
                f"LLM response value for year {point.year} exceeded the configured "
                f"{max_adjustment_pct:.1f}% adjustment limit"
            )

        validated_points.append(
            ForecastPoint(year=point.year, value=value, horizon=index + 1)
        )

    return validated_points


def _baseline_method_candidates(settings: LLMForecastSettings) -> list[str]:
    candidates: list[str] = []

    configured_method = str(settings.baseline_method).strip()
    if configured_method and configured_method != LLMForecastForecaster.method_id:
        candidates.append(configured_method)

    if "last_observed" not in candidates:
        candidates.append("last_observed")

    return candidates


def _env_text(name: str, default: str) -> str:
    return str(os.getenv(name, default)).strip()


def _env_int(name: str, default: int) -> int:
    try:
        return int(str(os.getenv(name, str(default))).strip())
    except ValueError:
        return int(default)


def _env_float(name: str, default: float) -> float:
    try:
        return float(str(os.getenv(name, str(default))).strip())
    except ValueError:
        return float(default)


def _env_bool(name: str, default: bool) -> bool:
    raw_value = os.getenv(name)
    if raw_value is None:
        return bool(default)

    return raw_value.strip().lower() in {"1", "true", "yes", "y", "on"}


def _has_remote_service_config(settings: LLMForecastSettings) -> bool:
    return bool(settings.service_url and settings.service_token)


def _remote_client_from_settings(
    settings: LLMForecastSettings,
    *,
    timeout_seconds: float | None = None,
) -> LLMForecastClient:
    try:
        from country_compare.prediction.llm.remote_client import RemoteLLMForecastClient
    except ImportError:
        return DisabledLLMForecastClient()

    return RemoteLLMForecastClient(
        service_url=settings.service_url,
        service_token=settings.service_token,
        timeout_seconds=timeout_seconds or settings.service_timeout_seconds,
        max_adjustment_pct=settings.max_adjustment_pct,
    )
