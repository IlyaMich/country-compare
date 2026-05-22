from __future__ import annotations

import pytest

from llm_forecast_service.errors import ServiceError
from llm_forecast_service.limits import enforce_request_limits
from llm_forecast_service.schemas import (
    ForecastAdjustmentOutput,
    ForecastAdjustmentRequest,
    ForecastConstraints,
    TimeSeriesPoint,
)
from llm_forecast_service.settings import ServiceSettings
from llm_forecast_service.validation import validate_candidate_output


def _request(
    *,
    history_count: int = 2,
    baseline_values: list[float] | None = None,
    max_adjustment_pct: float = 15.0,
) -> ForecastAdjustmentRequest:
    baseline_values = baseline_values or [100.0, 110.0]
    years = list(range(2030, 2030 + len(baseline_values)))
    return ForecastAdjustmentRequest(
        request_id="req-1",
        country_code="ISR",
        country_name="Israel",
        metric_id="gdp_per_capita",
        metric_name="GDP per capita",
        unit="USD",
        history=[
            TimeSeriesPoint(year=2020 + index, value=90.0 + index)
            for index in range(history_count)
        ],
        baseline_forecast=[
            TimeSeriesPoint(year=year, value=value)
            for year, value in zip(years, baseline_values, strict=True)
        ],
        constraints=ForecastConstraints(
            max_adjustment_pct=max_adjustment_pct,
            horizon_years=len(years),
            allowed_years=years,
        ),
        prompt_version="llm_forecast_mistral_v1",
    )


def test_enforce_request_limits_accepts_valid_request() -> None:
    enforce_request_limits(
        _request(), ServiceSettings(max_horizon_years=2, max_history_points=5)
    )


def test_enforce_request_limits_rejects_horizon_above_max() -> None:
    with pytest.raises(ServiceError) as exc_info:
        enforce_request_limits(_request(), ServiceSettings(max_horizon_years=1))

    assert exc_info.value.code == "limit_exceeded"


def test_enforce_request_limits_rejects_history_above_max() -> None:
    with pytest.raises(ServiceError) as exc_info:
        enforce_request_limits(
            _request(history_count=3), ServiceSettings(max_history_points=2)
        )

    assert exc_info.value.code == "limit_exceeded"


def test_enforce_request_limits_rejects_max_adjustment_above_service_limit() -> None:
    with pytest.raises(ServiceError) as exc_info:
        enforce_request_limits(
            _request(max_adjustment_pct=20.0),
            ServiceSettings(max_adjustment_pct=15.0),
        )

    assert exc_info.value.code == "limit_exceeded"


def test_enforce_request_limits_rejects_large_payload() -> None:
    with pytest.raises(ServiceError) as exc_info:
        enforce_request_limits(_request(), ServiceSettings(max_input_chars=10))

    assert exc_info.value.code == "limit_exceeded"


def test_validate_candidate_output_accepts_bounded_adjustment() -> None:
    request = _request()
    candidate = ForecastAdjustmentOutput(
        forecast_points=[
            TimeSeriesPoint(year=2030, value=110.0),
            TimeSeriesPoint(year=2031, value=121.0),
        ]
    )

    validated = validate_candidate_output(candidate, request)

    assert validated.forecast_points[0].value == 110.0


def test_validate_candidate_output_rejects_too_large_adjustment() -> None:
    request = _request()
    candidate = ForecastAdjustmentOutput(
        forecast_points=[
            TimeSeriesPoint(year=2030, value=130.0),
            TimeSeriesPoint(year=2031, value=110.0),
        ]
    )

    with pytest.raises(ServiceError) as exc_info:
        validate_candidate_output(candidate, request)

    assert exc_info.value.code == "adjustment_exceeds_limit"


def test_validate_candidate_output_rejects_near_zero_baseline_adjustment() -> None:
    request = _request(baseline_values=[0.0])
    candidate = ForecastAdjustmentOutput(
        forecast_points=[TimeSeriesPoint(year=2030, value=0.01)]
    )

    with pytest.raises(ServiceError) as exc_info:
        validate_candidate_output(candidate, request)

    assert exc_info.value.code == "adjustment_exceeds_limit"
