from __future__ import annotations

import asyncio
import json
import logging
import re
import time
import uuid
from collections.abc import Awaitable, Callable
from typing import Any

from fastapi import Depends, FastAPI, Request, Response
from fastapi.responses import JSONResponse

from llm_forecast_service import metrics
from llm_forecast_service.errors import ServiceError, register_exception_handlers
from llm_forecast_service.limits import enforce_request_limits
from llm_forecast_service.privacy import safe_metadata
from llm_forecast_service.providers import (
    BaselineEchoProvider,
    LLMProvider,
    MistralProvider,
)
from llm_forecast_service.schemas import (
    ForecastAdjustmentRequest,
    ForecastAdjustmentResponse,
    HealthResponse,
)
from llm_forecast_service.security import has_valid_service_token, require_service_token
from llm_forecast_service.settings import ServiceSettings
from llm_forecast_service.validation import validate_candidate_output

SERVICE_NAME = "llm-forecast-service"
_REQUEST_ID_RE = re.compile(r"^[A-Za-z0-9._:-]{1,200}$")

_PROVIDER_ERROR_CODES = frozenset(
    {
        "llm_provider_not_configured",
        "llm_provider_unavailable",
        "llm_timeout",
        "llm_rate_limited",
        "llm_response_invalid",
        "llm_schema_parse_failed",
        "forecast_adjustment_rejected",
    }
)

logger = logging.getLogger(__name__)
access_logger = logging.getLogger("llm_forecast_service.access")


def _configure_logging(log_level: str) -> None:
    root = logging.getLogger()
    root.setLevel(log_level.upper())
    if not root.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter("%(message)s"))
        root.addHandler(handler)


def _valid_or_new_request_id(raw_request_id: str | None) -> str:
    if raw_request_id and _REQUEST_ID_RE.fullmatch(raw_request_id):
        return raw_request_id
    return uuid.uuid4().hex


def _json_log(logger_: logging.Logger, event: str, **fields: Any) -> None:
    logger_.info(json.dumps({"event": event, **fields}, separators=(",", ":")))


def _llm_calls_for_provider(provider: LLMProvider) -> int:
    return 1 if provider.provider_name == "mistral" else 0


def _provider_model(provider: LLMProvider, settings: ServiceSettings) -> str:
    model = getattr(provider, "model_name", "")
    if isinstance(model, str) and model:
        return model
    if provider.provider_name == "mistral":
        return settings.mistral_model
    return provider.provider_name


def _log_forecast_adjust_request(
    *,
    request: ForecastAdjustmentRequest,
    http_request_id: str,
    provider_name: str,
    model: str,
    status: str,
    latency_ms: int,
    queue_wait_ms: int,
    llm_calls: int,
    error_code: str | None,
) -> None:
    # Keep the legacy key=value fields for existing log assertions, while avoiding
    # request bodies, prompt text, provider responses, tokens, and API keys.
    logger.info(
        "llm_forecast_adjust_completed "
        "request_id=%s http_request_id=%s country_code=%s metric_id=%s horizon_years=%s "
        "provider=%s model=%s status=%s latency_ms=%s queue_wait_ms=%s "
        "llm_calls=%s error_code=%s",
        request.request_id,
        http_request_id,
        request.country_code,
        request.metric_id,
        request.constraints.horizon_years,
        provider_name,
        model,
        status,
        latency_ms,
        queue_wait_ms,
        llm_calls,
        error_code or "",
    )


def build_provider(settings: ServiceSettings) -> LLMProvider:
    if settings.provider == "baseline_echo":
        return BaselineEchoProvider()
    return MistralProvider(settings)


async def _acquire_forecast_slot(
    semaphore: asyncio.Semaphore,
    settings: ServiceSettings,
) -> int:
    started_at = time.perf_counter()

    try:
        await asyncio.wait_for(
            semaphore.acquire(), timeout=settings.queue_timeout_seconds
        )
    except TimeoutError as exc:
        metrics.record_queue_rejection()
        metrics.observe_queue_wait(duration_seconds=settings.queue_timeout_seconds)
        raise ServiceError(
            code="service_overloaded",
            message="LLM forecast service is busy. Please retry later.",
            status_code=429,
            details={"queue_timeout_seconds": settings.queue_timeout_seconds},
        ) from exc

    queue_wait_seconds = time.perf_counter() - started_at
    metrics.observe_queue_wait(duration_seconds=queue_wait_seconds)
    return int(queue_wait_seconds * 1000)


def create_app(
    settings: ServiceSettings | None = None,
    provider: LLMProvider | None = None,
) -> FastAPI:
    resolved_settings = settings or ServiceSettings.from_env()

    app = FastAPI(title="LLM Forecast Service")
    app.state.settings = resolved_settings

    _configure_logging(resolved_settings.log_level.upper())

    app.state.provider = provider or build_provider(resolved_settings)
    app.state.forecast_semaphore = asyncio.Semaphore(
        max(1, resolved_settings.max_concurrent_requests)
    )
    app.state.inflight_forecast_requests = 0

    register_exception_handlers(app)

    @app.middleware("http")
    async def request_context_middleware(
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        started_at = time.perf_counter()
        request_id = _valid_or_new_request_id(request.headers.get("X-Request-ID"))
        request.state.request_id = request_id

        response: Response | None = None
        status_code = 500

        try:
            response = await call_next(request)
            status_code = response.status_code
            return response
        except Exception as exc:
            metrics.record_exception(exc_type=type(exc).__name__)
            status_code = 500
            raise
        finally:
            duration_seconds = time.perf_counter() - started_at
            duration_ms = int(duration_seconds * 1000)

            if response is not None:
                response.headers["X-Request-ID"] = request_id

            metrics.record_http_request(
                method=request.method,
                path=request.url.path,
                status_code=status_code,
                duration_seconds=duration_seconds,
            )

            _json_log(
                access_logger,
                "http_request_completed",
                request_id=request_id,
                method=request.method,
                path=request.url.path,
                status_code=status_code,
                duration_ms=duration_ms,
            )

    @app.get("/health", response_model=HealthResponse)
    async def health() -> HealthResponse:
        return HealthResponse(status="ok", service=SERVICE_NAME)

    @app.get("/ready", response_model=None)
    def ready(request: Request) -> JSONResponse:
        issues = resolved_settings.readiness_issues()
        provider_ = app.state.provider
        status = "ready" if not issues else "not_ready"

        include_details = (
            not resolved_settings.protect_ready_details
            or has_valid_service_token(request)
        )

        payload: dict[str, object] = {
            "status": status,
            "service": SERVICE_NAME,
        }

        if include_details:
            payload.update(
                {
                    "provider": provider_.provider_name,
                    "model": _provider_model(provider_, resolved_settings),
                    "deployment_profile": resolved_settings.deployment_profile,
                    "zdr_required": resolved_settings.require_zdr,
                    "zdr_confirmed": resolved_settings.mistral_zdr_confirmed,
                    "debug_payload_logging_enabled": (
                        resolved_settings.effective_debug_log_payloads
                    ),
                    "issues": issues,
                }
            )

        return JSONResponse(status_code=503 if issues else 200, content=payload)

    if resolved_settings.enable_metrics:
        metrics_dependencies = (
            [Depends(require_service_token)]
            if resolved_settings.protect_metrics
            else []
        )

        @app.get(
            "/metrics",
            include_in_schema=False,
            dependencies=metrics_dependencies,
        )
        def prometheus_metrics() -> Response:
            return Response(
                content=metrics.render_metrics(),
                media_type="text/plain; version=0.0.4; charset=utf-8",
            )

    @app.get("/v1/capabilities", dependencies=[Depends(require_service_token)])
    def capabilities() -> dict[str, object]:
        settings_ = app.state.settings
        issues = settings_.readiness_issues()

        if issues:
            raise ServiceError(
                code="service_not_ready",
                message="LLM forecast service is not ready.",
                status_code=503,
                details={"issues": issues},
            )

        provider_ = app.state.provider

        return {
            "provider": provider_.provider_name,
            "model": _provider_model(provider_, settings_),
            "supports_structured_output": True,
            "supports_bounded_adjustment": True,
            "max_series_per_request": settings_.max_series_per_request,
            "max_horizon_years": settings_.max_horizon_years,
            "max_history_points": settings_.max_history_points,
            "max_input_chars": settings_.max_input_chars,
            "max_output_tokens": settings_.max_output_tokens,
            "one_call_per_series": True,
            "zdr_required": settings_.require_zdr,
            "zdr_confirmed": settings_.mistral_zdr_confirmed,
            "deployment_profile": settings_.deployment_profile,
        }

    @app.post(
        "/v1/forecast/adjust",
        response_model=ForecastAdjustmentResponse,
        dependencies=[Depends(require_service_token)],
    )
    async def forecast_adjust(
        request: ForecastAdjustmentRequest,
        http_request: Request,
    ) -> ForecastAdjustmentResponse:
        started_at = time.perf_counter()
        queue_wait_ms = 0
        provider_latency_ms = 0
        status = "error"
        error_code: str | None = None
        acquired = False

        provider_ = app.state.provider
        provider_name = provider_.provider_name
        provider_model = _provider_model(provider_, resolved_settings)
        llm_calls = _llm_calls_for_provider(provider_)

        try:
            issues = resolved_settings.readiness_issues()
            if issues:
                raise ServiceError(
                    code="service_not_ready",
                    message="LLM forecast service is not ready.",
                    status_code=503,
                    details={"issues": issues},
                )

            enforce_request_limits(request, resolved_settings)

            queue_wait_ms = await _acquire_forecast_slot(
                app.state.forecast_semaphore,
                resolved_settings,
            )
            acquired = True

            app.state.inflight_forecast_requests += 1
            metrics.set_inflight_requests(app.state.inflight_forecast_requests)

            provider_started_at = time.perf_counter()
            try:
                raw_candidate = await provider_.generate_adjustment(request)
            finally:
                provider_latency_seconds = time.perf_counter() - provider_started_at
                provider_latency_ms = int(provider_latency_seconds * 1000)
                metrics.record_provider_duration(
                    provider=provider_name,
                    model=provider_model,
                    duration_seconds=provider_latency_seconds,
                )

            candidate = validate_candidate_output(raw_candidate, request)

            latency_ms = int((time.perf_counter() - started_at) * 1000)
            status = "ok"

            return ForecastAdjustmentResponse(
                forecast_points=candidate.forecast_points,
                rationale=candidate.rationale,
                assumptions=candidate.assumptions,
                warnings=candidate.warnings,
                metadata=safe_metadata(
                    {
                        "provider": provider_name,
                        "model": provider_model,
                        "prompt_version": request.prompt_version,
                        "llm_calls": llm_calls,
                        "latency_ms": latency_ms,
                        "total_latency_ms": latency_ms,
                        "provider_latency_ms": provider_latency_ms,
                        "queue_wait_ms": queue_wait_ms,
                        "deployment_profile": resolved_settings.deployment_profile,
                        "structured_output": True,
                        "bounded_adjustment": True,
                        "zdr_required": resolved_settings.require_zdr,
                        "zdr_confirmed": resolved_settings.mistral_zdr_confirmed,
                        "max_horizon_years": resolved_settings.max_horizon_years,
                        "max_history_points": resolved_settings.max_history_points,
                        "max_input_chars": resolved_settings.max_input_chars,
                        "max_output_tokens": resolved_settings.max_output_tokens,
                        "max_adjustment_pct": resolved_settings.max_adjustment_pct,
                        "max_concurrent_requests": resolved_settings.max_concurrent_requests,
                    }
                ),
            )

        except ServiceError as exc:
            error_code = exc.code
            if exc.code in _PROVIDER_ERROR_CODES:
                metrics.record_provider_error(
                    provider=provider_name,
                    error_code=exc.code,
                )
            raise

        except Exception:
            error_code = "internal_error"
            raise

        finally:
            if acquired:
                app.state.inflight_forecast_requests = max(
                    0,
                    app.state.inflight_forecast_requests - 1,
                )
                metrics.set_inflight_requests(app.state.inflight_forecast_requests)
                app.state.forecast_semaphore.release()

            latency_seconds = time.perf_counter() - started_at
            latency_ms = int(latency_seconds * 1000)

            metrics.record_forecast_request(
                status=status,
                provider=provider_name,
                error_code=error_code,
                duration_seconds=latency_seconds,
            )

            _log_forecast_adjust_request(
                request=request,
                http_request_id=getattr(http_request.state, "request_id", ""),
                provider_name=provider_name,
                model=provider_model,
                status=status,
                latency_ms=latency_ms,
                queue_wait_ms=queue_wait_ms,
                llm_calls=llm_calls if status == "ok" else 0,
                error_code=error_code,
            )

    return app


app = create_app()
