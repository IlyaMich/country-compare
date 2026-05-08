from __future__ import annotations

from typing import Annotated, Any, TypeAlias

from fastapi import APIRouter, Depends, Request, status
from fastapi.responses import JSONResponse

from country_compare.api.dependencies import get_app_facade
from country_compare.api.limits import (
    enforce_country_limit,
    enforce_horizon_limit,
    enforce_metric_limit,
)
from country_compare.api.schemas.common import ResultEnvelope
from country_compare.api.schemas.prediction import (
    BacktestPredictionRequest,
    PredictedMultiMetricComparisonRequest,
    PredictedProfileComparisonRequest,
    PredictedSingleMetricComparisonRequest,
    PredictionComparisonOptions,
    SingleMetricPredictionRequest,
)
from country_compare.api.serialization import (
    DEFAULT_MAX_RECORDS,
    serialize_result_envelope,
)
from country_compare.services.facade import AppFacade

router = APIRouter()

FacadeDependency: TypeAlias = Annotated[AppFacade, Depends(get_app_facade)]

_ERROR_RESPONSES: dict[int | str, dict[str, Any]] = {
    status.HTTP_400_BAD_REQUEST: {"model": ResultEnvelope},
    status.HTTP_404_NOT_FOUND: {"model": ResultEnvelope},
    status.HTTP_409_CONFLICT: {"model": ResultEnvelope},
    status.HTTP_500_INTERNAL_SERVER_ERROR: {"model": ResultEnvelope},
}


@router.post(
    "/single-metric",
    response_model=ResultEnvelope,
    responses=_ERROR_RESPONSES,
)
def predict_single_metric(
    body: SingleMetricPredictionRequest,
    request: Request,
    facade: FacadeDependency,
) -> ResultEnvelope | JSONResponse:
    """Forecast one metric for one or more countries."""

    enforce_country_limit(request, body.country_codes)
    enforce_horizon_limit(request, body.horizon_years)

    result = facade.predict_single_metric_for_countries(
        metric_id=body.metric_id,
        country_codes=body.country_codes,
        horizon_years=body.horizon_years,
        method=body.method,
        fallback_method=body.fallback_method,
        include_actuals=body.include_actuals,
        history_start_year=body.history_start_year,
        history_end_year=body.history_end_year,
        fail_fast=False,
        scenario_id=body.scenario_id,
    )
    return _prediction_response(
        result,
        request=request,
        mode="single_metric_countries_prediction",
    )


@router.post(
    "/backtest",
    response_model=ResultEnvelope,
    responses=_ERROR_RESPONSES,
)
def backtest_prediction(
    body: BacktestPredictionRequest,
    request: Request,
    facade: FacadeDependency,
) -> ResultEnvelope | JSONResponse:
    """Run a holdout backtest for one country/metric series."""

    enforce_country_limit(request, body.country_codes)

    result = facade.backtest_prediction(
        country_code=body.country_code,
        metric_id=body.metric_id,
        method=body.method,
        fallback_method=body.fallback_method,
        holdout_years=body.holdout_years,
        history_start_year=body.history_start_year,
        history_end_year=body.history_end_year,
        scenario_id=body.scenario_id,
    )
    return _prediction_response(
        result,
        request=request,
        mode="prediction_backtest",
    )


@router.post(
    "/compare/single-metric",
    response_model=ResultEnvelope,
    responses=_ERROR_RESPONSES,
)
def compare_predicted_single_metric(
    body: PredictedSingleMetricComparisonRequest,
    request: Request,
    facade: FacadeDependency,
) -> ResultEnvelope | JSONResponse:
    """Compare countries using a selected future forecast for one metric."""

    enforce_country_limit(request, body.country_codes)
    enforce_horizon_limit(request, body.horizon_years)

    result = facade.compare_predicted_single_metric(
        metric_id=body.metric_id,
        country_codes=body.country_codes,
        horizon_years=body.horizon_years,
        forecast_year=body.forecast_year,
        forecast_horizon=body.forecast_horizon,
        method=body.method,
        fallback_method=body.fallback_method,
        comparison_options=_comparison_options(body.comparison_options),
    )
    return _prediction_response(
        result,
        request=request,
        mode="predicted_single_metric_comparison",
    )


@router.post(
    "/compare/profile",
    response_model=ResultEnvelope,
    responses=_ERROR_RESPONSES,
)
def compare_predicted_profile(
    body: PredictedProfileComparisonRequest,
    request: Request,
    facade: FacadeDependency,
) -> ResultEnvelope | JSONResponse:
    """Compare countries using a selected future forecast and scoring profile."""

    enforce_country_limit(request, body.country_codes)
    enforce_horizon_limit(request, body.horizon_years)

    result = facade.compare_predicted_profile(
        profile_name=body.profile_name,
        country_codes=body.country_codes,
        horizon_years=body.horizon_years,
        forecast_year=body.forecast_year,
        forecast_horizon=body.forecast_horizon,
        method=body.method,
        fallback_method=body.fallback_method,
        comparison_options=_comparison_options(body.comparison_options),
    )
    return _prediction_response(
        result,
        request=request,
        mode="predicted_profile_comparison",
    )


@router.post(
    "/compare/multi-metric",
    response_model=ResultEnvelope,
    responses=_ERROR_RESPONSES,
)
def compare_predicted_multi_metric(
    body: PredictedMultiMetricComparisonRequest,
    request: Request,
    facade: FacadeDependency,
) -> ResultEnvelope | JSONResponse:
    """Compare countries using selected future forecasts for multiple metrics."""

    enforce_country_limit(request, body.country_codes)
    enforce_metric_limit(request, body.metric_ids)
    enforce_horizon_limit(request, body.horizon_years)

    result = facade.compare_predicted_multi_metric(
        metric_ids=body.metric_ids,
        country_codes=body.country_codes,
        horizon_years=body.horizon_years,
        forecast_year=body.forecast_year,
        forecast_horizon=body.forecast_horizon,
        method=body.method,
        fallback_method=body.fallback_method,
        comparison_options=_comparison_options(body.comparison_options),
    )
    return _prediction_response(
        result,
        request=request,
        mode="predicted_multi_metric_comparison",
    )


def _prediction_response(
    result: Any,
    *,
    request: Request,
    mode: str,
) -> ResultEnvelope | JSONResponse:
    envelope = serialize_result_envelope(
        result,
        mode=mode,
        max_records=_max_records_from_request(request),
    )

    if envelope.ok:
        return envelope

    return JSONResponse(
        status_code=_status_for_envelope(envelope),
        content=envelope.model_dump(mode="json"),
    )


def _comparison_options(
    options: PredictionComparisonOptions | None,
) -> dict[str, object] | None:
    if options is None:
        return None
    return options.to_service_options()


def _max_records_from_request(request: Request) -> int:
    api_settings = getattr(request.app.state, "api_settings", None)
    raw_max_records = getattr(api_settings, "max_records", DEFAULT_MAX_RECORDS)
    return int(raw_max_records)


def _status_for_envelope(envelope: ResultEnvelope) -> int:
    error = envelope.error
    if error is None:
        return status.HTTP_500_INTERNAL_SERVER_ERROR

    if error.code in {"missing_country", "missing_metric", "resource_not_found"}:
        return status.HTTP_404_NOT_FOUND
    if error.code in {
        "configuration_invalid",
        "config_invalid",
        "dataset_invalid",
        "state_invalid",
    }:
        return status.HTTP_409_CONFLICT
    if error.code in {
        "comparison_bridge_failed",
        "empty_country_selection",
        "empty_metric_selection",
        "empty_series",
        "evaluation_failed",
        "forecasting_failed",
        "input_invalid",
        "insufficient_history",
        "invalid_forecast_selection",
        "invalid_horizon",
        "non_numeric_value",
        "selection_invalid",
        "unsupported_method",
        "unsupported_series_shape",
        "input_limit_exceeded",
        "validation_failed",
    }:
        return status.HTTP_400_BAD_REQUEST

    return status.HTTP_500_INTERNAL_SERVER_ERROR
