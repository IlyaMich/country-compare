from __future__ import annotations

import json
from typing import Any

from llm_forecast_service.errors import ServiceError
from llm_forecast_service.schemas import ForecastAdjustmentRequest
from llm_forecast_service.settings import ServiceSettings


def enforce_request_limits(
    request: ForecastAdjustmentRequest,
    settings: ServiceSettings,
) -> None:
    issues: list[str] = []

    history_count = len(request.history)
    baseline_count = len(request.baseline_forecast)
    allowed_year_count = len(request.constraints.allowed_years)
    horizon_years = request.constraints.horizon_years
    estimated_input_chars = estimate_input_chars(request)

    if horizon_years > settings.max_horizon_years:
        issues.append(
            f"horizon_years exceeds limit: {horizon_years} > {settings.max_horizon_years}"
        )

    if baseline_count > settings.max_horizon_years:
        issues.append(
            "baseline_forecast length exceeds limit: "
            f"{baseline_count} > {settings.max_horizon_years}"
        )

    if history_count > settings.max_history_points:
        issues.append(
            f"history length exceeds limit: {history_count} > {settings.max_history_points}"
        )

    if estimated_input_chars > settings.max_input_chars:
        issues.append(
            "estimated input size exceeds limit: "
            f"{estimated_input_chars} > {settings.max_input_chars}"
        )

    if request.constraints.max_adjustment_pct > settings.max_adjustment_pct:
        issues.append(
            "requested max_adjustment_pct exceeds service limit: "
            f"{request.constraints.max_adjustment_pct} > {settings.max_adjustment_pct}"
        )

    if allowed_year_count != horizon_years:
        issues.append(
            "allowed_years length must match horizon_years: "
            f"{allowed_year_count} != {horizon_years}"
        )

    if baseline_count != horizon_years:
        issues.append(
            "baseline_forecast length must match horizon_years: "
            f"{baseline_count} != {horizon_years}"
        )

    baseline_years = [point.year for point in request.baseline_forecast]
    allowed_years = list(request.constraints.allowed_years)
    if baseline_years != allowed_years:
        issues.append("baseline_forecast years must exactly match allowed_years")

    if issues:
        raise ServiceError(
            code="limit_exceeded",
            message="LLM forecast request exceeds configured service limits.",
            status_code=400,
            details={
                "issues": issues,
                "estimated_input_chars": estimated_input_chars,
                "limits": {
                    "max_horizon_years": settings.max_horizon_years,
                    "max_history_points": settings.max_history_points,
                    "max_input_chars": settings.max_input_chars,
                    "max_output_tokens": settings.max_output_tokens,
                    "max_adjustment_pct": settings.max_adjustment_pct,
                },
            },
        )


def estimate_input_chars(request: ForecastAdjustmentRequest) -> int:
    payload: dict[str, Any] = request.model_dump(mode="json")
    return len(json.dumps(payload, ensure_ascii=False, separators=(",", ":")))
