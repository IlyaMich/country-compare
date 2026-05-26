from __future__ import annotations

from fastapi import Depends, FastAPI
from fastapi.responses import JSONResponse

from llm_forecast_service import __version__
from llm_forecast_service.errors import ServiceError, register_exception_handlers
from llm_forecast_service.limits import enforce_request_limits
from llm_forecast_service.providers import (
    BaselineEchoProvider,
    LLMProvider,
    MistralProvider,
)
from llm_forecast_service.schemas import (
    CapabilitiesResponse,
    ForecastAdjustmentRequest,
    ForecastAdjustmentResponse,
    HealthResponse,
    ReadyResponse,
)
from llm_forecast_service.security import require_service_token
from llm_forecast_service.settings import ServiceSettings
from llm_forecast_service.validation import validate_candidate_output

SERVICE_NAME = "llm-forecast-service"


def build_provider(settings: ServiceSettings) -> LLMProvider:
    if settings.provider == "mistral" and settings.mistral_api_key:
        return MistralProvider(settings)
    return BaselineEchoProvider()


def create_app(
    settings: ServiceSettings | None = None,
    provider: LLMProvider | None = None,
) -> FastAPI:
    app = FastAPI(title="Country Compare LLM Forecast Service", version=__version__)
    app.state.settings = settings or ServiceSettings.from_env()
    app.state.provider = provider or build_provider(app.state.settings)
    register_exception_handlers(app)

    @app.get("/health", response_model=HealthResponse)
    async def health() -> HealthResponse:
        return HealthResponse(status="ok", service=SERVICE_NAME)

    @app.get("/ready", response_model=ReadyResponse)
    async def ready() -> ReadyResponse | JSONResponse:
        current_settings: ServiceSettings = app.state.settings
        issues = current_settings.readiness_issues()
        response = ReadyResponse(
            status="ready" if not issues else "not_ready",
            provider=current_settings.provider if not issues else None,
            model=current_settings.mistral_model if not issues else None,
            deployment_profile=current_settings.deployment_profile,
            zdr_required=current_settings.require_zdr,
            zdr_confirmed=current_settings.mistral_zdr_confirmed,
            issues=issues,
        )
        if issues:
            return JSONResponse(status_code=503, content=response.model_dump())
        return response

    @app.get(
        "/v1/capabilities",
        response_model=CapabilitiesResponse,
        dependencies=[Depends(require_service_token)],
    )
    async def capabilities() -> CapabilitiesResponse:
        current_settings: ServiceSettings = app.state.settings
        issues = current_settings.readiness_issues()
        if issues:
            raise ServiceError(
                "service_not_ready",
                "LLM forecast service is not ready.",
                status_code=503,
                details={"issues": issues},
            )
        return CapabilitiesResponse(
            provider=current_settings.provider,
            model=current_settings.mistral_model,
            supports_structured_output=True,
            supports_bounded_adjustment=True,
            max_series_per_request=current_settings.max_series_per_request,
            max_horizon_years=current_settings.max_horizon_years,
            max_history_points=current_settings.max_history_points,
            one_call_per_series=True,
            zdr_required=current_settings.require_zdr,
            zdr_confirmed=current_settings.mistral_zdr_confirmed,
        )

    @app.post(
        "/v1/forecast/adjust",
        response_model=ForecastAdjustmentResponse,
        dependencies=[Depends(require_service_token)],
    )
    async def forecast_adjust(
        request: ForecastAdjustmentRequest,
    ) -> ForecastAdjustmentResponse:
        current_settings: ServiceSettings = app.state.settings
        issues = current_settings.readiness_issues()
        if issues:
            raise ServiceError(
                "service_not_ready",
                "LLM forecast service is not ready.",
                status_code=503,
                details={"issues": issues},
            )

        enforce_request_limits(request, current_settings)
        raw_candidate = await app.state.provider.generate_adjustment(request)
        candidate = validate_candidate_output(raw_candidate, request)
        return ForecastAdjustmentResponse(
            forecast_points=candidate.forecast_points,
            rationale=candidate.rationale,
            assumptions=candidate.assumptions,
            warnings=candidate.warnings,
            metadata={
                "provider": current_settings.provider,
                "model": current_settings.mistral_model,
                "prompt_version": request.prompt_version,
                "llm_calls": 1 if app.state.provider.provider_name == "mistral" else 0,
            },
        )

    return app


app = create_app()
