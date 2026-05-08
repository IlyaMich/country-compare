from __future__ import annotations

from collections.abc import Iterable

import pandas as pd

from country_compare.prediction.errors import PredictionErrorCode, PredictionException
from country_compare.prediction.models import (
    ForecasterInfo,
    ForecastOptions,
    MultiSeriesPredictionRequest,
    PredictionDiagnostics,
    PredictionDiagnosticStatus,
    PredictionError,
    PredictionMethod,
    PredictionResult,
    SingleMetricPredictionRequest,
)
from country_compare.prediction.output import (
    PREDICTION_CREATED_AT_COLUMN,
    PREDICTION_RUN_ID_COLUMN,
    new_prediction_run_id,
    order_prediction_columns,
    prediction_created_at_now,
)
from country_compare.prediction.single_metric import predict_single_metric
from country_compare.prediction.validation import validate_prediction_request


def predict_single_metric_for_countries(
    canonical_df: pd.DataFrame,
    *,
    metric_id: str,
    country_codes: Iterable[str],
    horizon_years: int,
    method: PredictionMethod | str | None = None,
    fallback_method: PredictionMethod | str | None = PredictionMethod.LAST_OBSERVED,
    include_actuals: bool = True,
    history_start_year: int | None = None,
    history_end_year: int | None = None,
    fail_fast: bool = False,
    scenario_id: str = "baseline",
    options: ForecastOptions | None = None,
) -> PredictionResult:
    request = MultiSeriesPredictionRequest(
        country_codes=list(country_codes),
        metric_ids=[metric_id],
        horizon_years=horizon_years,
        method=method,
        include_actuals=include_actuals,
        history_start_year=history_start_year,
        history_end_year=history_end_year,
        fallback_method=fallback_method,
        fail_fast=fail_fast,
        scenario_id=scenario_id,
    )
    return _predict_multi_series(canonical_df, request, options=options)


def predict_metrics_for_country(
    canonical_df: pd.DataFrame,
    *,
    country_code: str,
    metric_ids: Iterable[str],
    horizon_years: int,
    method: PredictionMethod | str | None = None,
    fallback_method: PredictionMethod | str | None = PredictionMethod.LAST_OBSERVED,
    include_actuals: bool = True,
    history_start_year: int | None = None,
    history_end_year: int | None = None,
    fail_fast: bool = False,
    scenario_id: str = "baseline",
    options: ForecastOptions | None = None,
) -> PredictionResult:
    request = MultiSeriesPredictionRequest(
        country_codes=[country_code],
        metric_ids=list(metric_ids),
        horizon_years=horizon_years,
        method=method,
        include_actuals=include_actuals,
        history_start_year=history_start_year,
        history_end_year=history_end_year,
        fallback_method=fallback_method,
        fail_fast=fail_fast,
        scenario_id=scenario_id,
    )
    return _predict_multi_series(canonical_df, request, options=options)


def predict_metric_country_grid(
    canonical_df: pd.DataFrame,
    *,
    country_codes: Iterable[str],
    metric_ids: Iterable[str],
    horizon_years: int,
    method: PredictionMethod | str | None = None,
    fallback_method: PredictionMethod | str | None = PredictionMethod.LAST_OBSERVED,
    include_actuals: bool = True,
    history_start_year: int | None = None,
    history_end_year: int | None = None,
    fail_fast: bool = False,
    scenario_id: str = "baseline",
    options: ForecastOptions | None = None,
) -> PredictionResult:
    request = MultiSeriesPredictionRequest(
        country_codes=list(country_codes),
        metric_ids=list(metric_ids),
        horizon_years=horizon_years,
        method=method,
        include_actuals=include_actuals,
        history_start_year=history_start_year,
        history_end_year=history_end_year,
        fallback_method=fallback_method,
        fail_fast=fail_fast,
        scenario_id=scenario_id,
    )
    return _predict_multi_series(canonical_df, request, options=options)


def _predict_multi_series(
    canonical_df: pd.DataFrame,
    request: MultiSeriesPredictionRequest,
    *,
    options: ForecastOptions | None = None,
) -> PredictionResult:
    options = options or ForecastOptions(scenario_id=request.scenario_id)
    _validate_multi_series_request(request, options=options)

    prediction_run_id = new_prediction_run_id()
    prediction_created_at = prediction_created_at_now()

    forecast_parts: list[pd.DataFrame] = []
    combined_parts: list[pd.DataFrame] = []
    comparison_parts: list[pd.DataFrame] = []
    diagnostics: list[PredictionDiagnostics] = []
    forecaster_info: list[ForecasterInfo] = []
    successful_pairs: list[dict[str, str]] = []
    failed_pairs: list[dict[str, str]] = []

    for country_code in request.country_codes:
        for metric_id in request.metric_ids:
            single_request = SingleMetricPredictionRequest(
                country_code=country_code,
                metric_id=metric_id,
                horizon_years=request.horizon_years,
                method=request.method,
                include_actuals=request.include_actuals,
                history_start_year=request.history_start_year,
                history_end_year=request.history_end_year,
                fallback_method=request.fallback_method,
                fail_on_warning=False,
                scenario_id=request.scenario_id,
            )
            try:
                result = predict_single_metric(
                    canonical_df, single_request, options=options
                )
            except PredictionException as exc:
                if request.fail_fast:
                    raise
                diagnostics.append(
                    _diagnostics_from_exception(
                        exc,
                        requested_method=request.method,
                    )
                )
                failed_pairs.append(
                    {"country_code": country_code, "metric_id": metric_id}
                )
                continue

            forecast_parts.append(
                _apply_batch_run_metadata(
                    result.forecast_df,
                    prediction_run_id=prediction_run_id,
                    prediction_created_at=prediction_created_at,
                )
            )
            combined_parts.append(
                _apply_batch_run_metadata(
                    result.combined_df,
                    prediction_run_id=prediction_run_id,
                    prediction_created_at=prediction_created_at,
                )
            )
            comparison_parts.append(
                _apply_batch_run_metadata(
                    result.comparison_ready_df,
                    prediction_run_id=prediction_run_id,
                    prediction_created_at=prediction_created_at,
                )
            )
            diagnostics.extend(result.diagnostics)
            forecaster_info.extend(result.forecaster_info)
            successful_pairs.append(
                {"country_code": country_code, "metric_id": metric_id}
            )

    forecast_df = _concat_prediction_frames(forecast_parts)
    combined_df = _concat_prediction_frames(combined_parts)
    comparison_ready_df = _concat_prediction_frames(comparison_parts)

    return PredictionResult(
        request=request,
        forecast_df=forecast_df,
        combined_df=combined_df,
        comparison_ready_df=comparison_ready_df,
        diagnostics=diagnostics,
        forecaster_info=forecaster_info,
        metadata={
            "prediction_run_id": prediction_run_id,
            "prediction_created_at": prediction_created_at,
            "successful_series_count": len(successful_pairs),
            "failed_series_count": len(failed_pairs),
            "successful_pairs": successful_pairs,
            "failed_pairs": failed_pairs,
            "all_series_failed": bool(diagnostics) and not successful_pairs,
        },
    )


def _validate_multi_series_request(
    request: MultiSeriesPredictionRequest,
    *,
    options: ForecastOptions,
) -> None:
    if not request.country_codes:
        raise PredictionException(
            PredictionErrorCode.EMPTY_COUNTRY_SELECTION,
            "country_codes must contain at least one country code",
            details={"country_codes": request.country_codes},
        )
    if not request.metric_ids:
        raise PredictionException(
            PredictionErrorCode.EMPTY_METRIC_SELECTION,
            "metric_ids must contain at least one metric id",
            details={"metric_ids": request.metric_ids},
        )

    validation_request = SingleMetricPredictionRequest(
        country_code=request.country_codes[0],
        metric_id=request.metric_ids[0],
        horizon_years=request.horizon_years,
        method=request.method,
        include_actuals=request.include_actuals,
        history_start_year=request.history_start_year,
        history_end_year=request.history_end_year,
        fallback_method=request.fallback_method,
        fail_on_warning=False,
        scenario_id=request.scenario_id,
    )
    validate_prediction_request(validation_request, options=options)


def _diagnostics_from_exception(
    exc: PredictionException,
    *,
    requested_method: PredictionMethod | str | None,
) -> PredictionDiagnostics:
    return PredictionDiagnostics(
        status=PredictionDiagnosticStatus.FAILED,
        country_code=exc.country_code,
        metric_id=exc.metric_id,
        method_requested=(
            str(requested_method) if requested_method is not None else None
        ),
        method_used=None,
        fallback_used=False,
        history_observation_count=0,
        training_start_year=None,
        training_end_year=None,
        forecast_origin_year=None,
        missing_years=[],
        warnings=[],
        errors=[
            PredictionError(
                code=exc.code,
                message=exc.message,
                country_code=exc.country_code,
                metric_id=exc.metric_id,
                year=exc.year,
                details=dict(exc.details),
            )
        ],
    )


def _apply_batch_run_metadata(
    dataframe: pd.DataFrame,
    *,
    prediction_run_id: str,
    prediction_created_at: str,
) -> pd.DataFrame:
    result = dataframe.copy(deep=True)
    if result.empty:
        return order_prediction_columns(result)
    result[PREDICTION_RUN_ID_COLUMN] = prediction_run_id
    result[PREDICTION_CREATED_AT_COLUMN] = prediction_created_at
    return order_prediction_columns(result)


def _concat_prediction_frames(parts: list[pd.DataFrame]) -> pd.DataFrame:
    if not parts:
        return order_prediction_columns(pd.DataFrame())
    return order_prediction_columns(pd.concat(parts, ignore_index=True, sort=False))


__all__ = [
    "predict_single_metric_for_countries",
    "predict_metrics_for_country",
    "predict_metric_country_grid",
]
