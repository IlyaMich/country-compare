from __future__ import annotations

import asyncio
import logging
import time

from fastapi import Depends, FastAPI
from fastapi.responses import JSONResponse

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
from llm_forecast_service.security import require_service_token
from llm_forecast_service.settings import ServiceSettings
from llm_forecast_service.validation import validate_candidate_output

SERVICE_NAME = "llm-forecast-service"

logger = logging.getLogger(__name__)


def _llm_calls_for_provider(provider: LLMProvider) -> int:
    return 1 if provider.provider_name == "mistral" else 0


def _log_forecast_adjust_request(
    *,
    request: ForecastAdjustmentRequest,
    provider_name: str,
    model: str,
    status: str,
    latency_ms: int,
    queue_wait_ms: int,
    llm_calls: int,
    error_code: str | None,
) -> None:
    logger.info(
        "llm_forecast_adjust_completed "
        "request_id=%s country_code=%s metric_id=%s horizon_years=%s "
        "provider=%s model=%s status=%s latency_ms=%s queue_wait_ms=%s "
        "llm_calls=%s error_code=%s",
        request.request_id,
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
    if settings.provider == "mistral" and settings.mistral_api_key:
        return MistralProvider(settings)
    return BaselineEchoProvider()


def create_app(
    settings: ServiceSettings | None = None,
    provider: LLMProvider | None = None,
) -> FastAPI:
    resolved_settings = settings or ServiceSettings.from_env()

    app = FastAPI(title="LLM Forecast Service")
    app.state.settings = resolved_settings

    logging.basicConfig(level=resolved_settings.log_level.upper())

    app.state.provider = provider or build_provider(resolved_settings)
    app.state.provider = provider or build_provider(resolved_settings)
    app.state.forecast_semaphore = asyncio.Semaphore(
        resolved_settings.max_concurrent_requests
    )
    register_exception_handlers(app)

    @app.get("/health", response_model=HealthResponse)
    async def health() -> HealthResponse:
        return HealthResponse(status="ok", service=SERVICE_NAME)

    @app.get("/ready", response_model=None)
    def ready() -> JSONResponse:
        issues = resolved_settings.readiness_issues()

        payload: dict[str, object] = {
            "status": "ready" if not issues else "not_ready",
            "provider": resolved_settings.provider,
            "model": resolved_settings.mistral_model,
            "deployment_profile": resolved_settings.deployment_profile,
            "zdr_required": resolved_settings.require_zdr,
            "zdr_confirmed": resolved_settings.mistral_zdr_confirmed,
            "debug_payload_logging_enabled": (
                resolved_settings.effective_debug_log_payloads
            ),
            "issues": issues,
        }

        return JSONResponse(
            status_code=503 if issues else 200,
            content=payload,
        )

    @app.get("/v1/capabilities", dependencies=[Depends(require_service_token)])
    def capabilities() -> dict[str, object]:
        settings = app.state.settings
        issues = settings.readiness_issues()

        if issues:
            raise ServiceError(
                code="service_not_ready",
                message="LLM forecast service is not ready.",
                status_code=503,
                details={"issues": issues},
            )

        return {
            "provider": settings.provider,
            "model": resolved_settings.mistral_model,
            "supports_structured_output": True,
            "supports_bounded_adjustment": True,
            "max_series_per_request": settings.max_series_per_request,
            "max_horizon_years": settings.max_horizon_years,
            "max_history_points": settings.max_history_points,
            "max_input_chars": settings.max_input_chars,
            "max_output_tokens": settings.max_output_tokens,
            "one_call_per_series": True,
            "zdr_required": resolved_settings.require_zdr,
            "zdr_confirmed": settings.mistral_zdr_confirmed,
            "deployment_profile": resolved_settings.deployment_profile,
        }

    @app.post(
        "/v1/forecast/adjust",
        response_model=ForecastAdjustmentResponse,
        dependencies=[Depends(require_service_token)],
    )
    async def forecast_adjust(
        request: ForecastAdjustmentRequest,
    ) -> ForecastAdjustmentResponse:
        started_at = time.perf_counter()
        queue_wait_ms = 0
        status = "error"
        error_code: str | None = None

        provider = app.state.provider
        provider_name = provider.provider_name
        llm_calls = _llm_calls_for_provider(provider)

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

            queue_started_at = time.perf_counter()
            async with app.state.forecast_semaphore:
                queue_wait_ms = int((time.perf_counter() - queue_started_at) * 1000)
                raw_candidate = await provider.generate_adjustment(request)

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
                        "model": resolved_settings.mistral_model,
                        "prompt_version": request.prompt_version,
                        "llm_calls": llm_calls,
                        "latency_ms": latency_ms,
                        "queue_wait_ms": queue_wait_ms,
                        "deployment_profile": resolved_settings.deployment_profile,
                        "zdr_required": resolved_settings.require_zdr,
                        "zdr_confirmed": resolved_settings.mistral_zdr_confirmed,
                        "max_horizon_years": resolved_settings.max_horizon_years,
                        "max_history_points": resolved_settings.max_history_points,
                        "max_input_chars": resolved_settings.max_input_chars,
                        "max_output_tokens": resolved_settings.max_output_tokens,
                        "max_adjustment_pct": resolved_settings.max_adjustment_pct,
                        "max_concurrent_requests": (
                            resolved_settings.max_concurrent_requests
                        ),
                    }
                ),
            )

        except ServiceError as exc:
            error_code = exc.code
            raise

        except Exception:
            error_code = "unexpected_error"
            raise

        finally:
            latency_ms = int((time.perf_counter() - started_at) * 1000)
            _log_forecast_adjust_request(
                request=request,
                provider_name=provider_name,
                model=resolved_settings.mistral_model,
                status=status,
                latency_ms=latency_ms,
                queue_wait_ms=queue_wait_ms,
                llm_calls=llm_calls if status == "ok" else 0,
                error_code=error_code,
            )

    return app


app = create_app()
