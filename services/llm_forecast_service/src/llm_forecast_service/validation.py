from __future__ import annotations

import math

from llm_forecast_service.errors import ServiceError
from llm_forecast_service.schemas import (
    ForecastAdjustmentOutput,
    ForecastAdjustmentRequest,
)

_NEAR_ZERO_EPSILON = 1e-9
_PERCENT_TOLERANCE = 1e-9


def validate_candidate_output(
    candidate: ForecastAdjustmentOutput,
    request: ForecastAdjustmentRequest,
) -> ForecastAdjustmentOutput:
    points = candidate.forecast_points
    expected_years = request.constraints.allowed_years

    if len(points) != request.constraints.horizon_years:
        raise ServiceError(
            "invalid_provider_response",
            "Provider returned the wrong number of forecast points.",
            status_code=502,
            details={
                "forecast_point_count": len(points),
                "expected_count": request.constraints.horizon_years,
            },
        )

    years = [point.year for point in points]
    if len(set(years)) != len(years):
        raise ServiceError(
            "invalid_provider_response",
            "Provider returned duplicate forecast years.",
            status_code=502,
            details={"years": years},
        )
    if years != expected_years:
        raise ServiceError(
            "invalid_provider_response",
            "Provider returned forecast years that do not match requested years.",
            status_code=502,
            details={"years": years, "expected_years": expected_years},
        )

    baseline_by_year = {point.year: point.value for point in request.baseline_forecast}
    max_adjustment_pct = request.constraints.max_adjustment_pct
    for point in points:
        if not math.isfinite(point.value):
            raise ServiceError(
                "invalid_provider_response",
                "Provider returned a non-finite forecast value.",
                status_code=502,
                details={"year": point.year},
            )

        baseline_value = baseline_by_year[point.year]
        if abs(baseline_value) < _NEAR_ZERO_EPSILON:
            if point.value != baseline_value:
                raise ServiceError(
                    "adjustment_exceeds_limit",
                    "Provider adjusted a near-zero baseline value.",
                    status_code=502,
                    details={"year": point.year},
                )
            continue

        adjustment_pct = abs(point.value - baseline_value) / abs(baseline_value) * 100.0
        if adjustment_pct > max_adjustment_pct + _PERCENT_TOLERANCE:
            raise ServiceError(
                "adjustment_exceeds_limit",
                "Provider forecast exceeds the configured max adjustment percentage.",
                status_code=502,
                details={
                    "year": point.year,
                    "adjustment_pct": adjustment_pct,
                    "max_adjustment_pct": max_adjustment_pct,
                },
            )

    return candidate
