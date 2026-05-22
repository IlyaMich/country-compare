from __future__ import annotations

from llm_forecast_service.errors import ServiceError
from llm_forecast_service.schemas import ForecastAdjustmentRequest
from llm_forecast_service.settings import ServiceSettings


def enforce_request_limits(
    request: ForecastAdjustmentRequest, settings: ServiceSettings
) -> None:
    if request.constraints.horizon_years > settings.max_horizon_years:
        raise ServiceError(
            "limit_exceeded",
            "Forecast horizon exceeds service limit.",
            status_code=400,
            details={
                "horizon_years": request.constraints.horizon_years,
                "max_horizon_years": settings.max_horizon_years,
            },
        )
    if len(request.history) > settings.max_history_points:
        raise ServiceError(
            "limit_exceeded",
            "History length exceeds service limit.",
            status_code=400,
            details={
                "history_points": len(request.history),
                "max_history_points": settings.max_history_points,
            },
        )
    if request.constraints.max_adjustment_pct > settings.max_adjustment_pct:
        raise ServiceError(
            "limit_exceeded",
            "Requested max adjustment exceeds service limit.",
            status_code=400,
            details={
                "max_adjustment_pct": request.constraints.max_adjustment_pct,
                "service_max_adjustment_pct": settings.max_adjustment_pct,
            },
        )

    input_chars = len(request.model_dump_json())
    if input_chars > settings.max_input_chars:
        raise ServiceError(
            "limit_exceeded",
            "Request payload exceeds service input-size limit.",
            status_code=400,
            details={
                "input_chars": input_chars,
                "max_input_chars": settings.max_input_chars,
            },
        )
