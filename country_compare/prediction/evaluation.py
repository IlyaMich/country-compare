from __future__ import annotations

import math
from typing import Any

import pandas as pd

from country_compare.prediction.errors import PredictionErrorCode, PredictionException
from country_compare.prediction.models import (
    BacktestRequest,
    BacktestResult,
    ForecastOptions,
    ForecasterInfo,
    PredictionDiagnosticStatus,
    PredictionDiagnostics,
    PredictionError,
    PredictionMethod,
    SingleMetricPredictionRequest,
)
from country_compare.prediction.output import (
    DIAGNOSTIC_STATUS_COLUMN,
    FORECAST_HORIZON_COLUMN,
    FORECAST_ORIGIN_YEAR_COLUMN,
    PREDICTION_CREATED_AT_COLUMN,
    PREDICTION_METHOD_COLUMN,
    PREDICTION_RUN_ID_COLUMN,
    SCENARIO_ID_COLUMN,
    TRAINING_END_YEAR_COLUMN,
    TRAINING_START_YEAR_COLUMN,
    new_prediction_run_id,
    prediction_created_at_now,
)
from country_compare.prediction.registry import ForecasterRegistryError, resolve_forecaster
from country_compare.prediction.timeseries import prepare_metric_time_series
from country_compare.prediction.validation import (
    VALUE_COLUMN,
    YEAR_COLUMN,
    resolve_fallback_method,
    resolve_requested_method,
)

ACTUAL_VALUE_COLUMN = "actual_value"
PREDICTED_VALUE_COLUMN = "predicted_value"
ERROR_COLUMN = "error"
ABSOLUTE_ERROR_COLUMN = "absolute_error"
SQUARED_ERROR_COLUMN = "squared_error"
ABSOLUTE_PERCENTAGE_ERROR_COLUMN = "absolute_percentage_error"

EVALUATION_COLUMNS: tuple[str, ...] = (
    "country_code",
    "country_name",
    "metric_id",
    "metric_name",
    YEAR_COLUMN,
    ACTUAL_VALUE_COLUMN,
    PREDICTED_VALUE_COLUMN,
    ERROR_COLUMN,
    ABSOLUTE_ERROR_COLUMN,
    SQUARED_ERROR_COLUMN,
    ABSOLUTE_PERCENTAGE_ERROR_COLUMN,
    FORECAST_HORIZON_COLUMN,
    FORECAST_ORIGIN_YEAR_COLUMN,
    PREDICTION_METHOD_COLUMN,
    TRAINING_START_YEAR_COLUMN,
    TRAINING_END_YEAR_COLUMN,
    PREDICTION_RUN_ID_COLUMN,
    PREDICTION_CREATED_AT_COLUMN,
    SCENARIO_ID_COLUMN,
    DIAGNOSTIC_STATUS_COLUMN,
)


def backtest_series(
    canonical_df: pd.DataFrame,
    *,
    country_code: str,
    metric_id: str,
    method: PredictionMethod | str | None = PredictionMethod.LINEAR_TREND,
    fallback_method: PredictionMethod | str | None = PredictionMethod.LAST_OBSERVED,
    holdout_years: int = 3,
    history_start_year: int | None = None,
    history_end_year: int | None = None,
    scenario_id: str = "baseline",
    options: ForecastOptions | None = None,
) -> BacktestResult:
    """
    Evaluate one country/metric forecast with a latest-N-year holdout split.

    The backtest trains on observations before the holdout window, forecasts the
    held-out years, and compares predicted values against observed values.
    """
    request = BacktestRequest(
        country_code=country_code,
        metric_id=metric_id,
        holdout_years=holdout_years,
        method=method,
        fallback_method=fallback_method,
        history_start_year=history_start_year,
        history_end_year=history_end_year,
        scenario_id=scenario_id,
    )
    return _backtest_series_from_request(canonical_df, request, options=options)


def _backtest_series_from_request(
    canonical_df: pd.DataFrame,
    request: BacktestRequest,
    *,
    options: ForecastOptions | None = None,
) -> BacktestResult:
    options = options or ForecastOptions(scenario_id=request.scenario_id)
    _validate_backtest_request(request, options=options)

    full_prepared = prepare_metric_time_series(
        canonical_df,
        SingleMetricPredictionRequest(
            country_code=request.country_code,
            metric_id=request.metric_id,
            horizon_years=1,
            method=request.method,
            fallback_method=request.fallback_method,
            history_start_year=request.history_start_year,
            history_end_year=request.history_end_year,
            scenario_id=request.scenario_id,
        ),
    )

    full_series = full_prepared.series_df.copy(deep=True)
    if len(full_series.index) <= request.holdout_years:
        raise PredictionException(
            PredictionErrorCode.INSUFFICIENT_HISTORY,
            "backtest requires at least one training observation before the holdout window",
            country_code=request.country_code,
            metric_id=request.metric_id,
            details={
                "observation_count": int(len(full_series.index)),
                "holdout_years": request.holdout_years,
            },
        )

    train_df = full_series.iloc[: -request.holdout_years].copy()
    holdout_df = full_series.iloc[-request.holdout_years :].copy()

    train_end_year = int(pd.to_numeric(train_df[YEAR_COLUMN], errors="coerce").max())
    holdout_year_values = [
        int(year)
        for year in pd.to_numeric(holdout_df[YEAR_COLUMN], errors="coerce").dropna().tolist()
    ]

    train_prepared = prepare_metric_time_series(
        canonical_df,
        SingleMetricPredictionRequest(
            country_code=request.country_code,
            metric_id=request.metric_id,
            horizon_years=request.holdout_years,
            method=request.method,
            fallback_method=request.fallback_method,
            history_start_year=request.history_start_year,
            history_end_year=train_end_year,
            scenario_id=request.scenario_id,
        ),
    )

    requested_method = resolve_requested_method(
        SingleMetricPredictionRequest(
            country_code=request.country_code,
            metric_id=request.metric_id,
            horizon_years=request.holdout_years,
            method=request.method,
            fallback_method=request.fallback_method,
            scenario_id=request.scenario_id,
        )
    )
    fallback_method = resolve_fallback_method(
        SingleMetricPredictionRequest(
            country_code=request.country_code,
            metric_id=request.metric_id,
            horizon_years=request.holdout_years,
            method=request.method,
            fallback_method=request.fallback_method,
            scenario_id=request.scenario_id,
        )
    )

    selected_forecaster, fallback_used, method_warnings = _select_forecaster(
        requested_method=requested_method,
        fallback_method=fallback_method,
        train_series=train_prepared.series_df,
        diagnostics_context=train_prepared.context,
        options=options,
    )

    warnings = [*full_prepared.warnings, *train_prepared.warnings, *method_warnings]
    expected_consecutive_years = [
        train_end_year + offset for offset in range(1, request.holdout_years + 1)
    ]
    if holdout_year_values != expected_consecutive_years:
        warnings.append(
            "holdout years are not consecutive after the training end year; "
            "forecaster was evaluated directly on observed holdout years"
        )

    status = PredictionDiagnosticStatus.WARNING if warnings else PredictionDiagnosticStatus.OK
    diagnostics = PredictionDiagnostics(
        status=status,
        country_code=request.country_code,
        metric_id=request.metric_id,
        method_requested=requested_method.value,
        method_used=selected_forecaster.method_id,
        fallback_used=fallback_used,
        history_observation_count=train_prepared.context.history_observation_count,
        training_start_year=train_prepared.context.training_start_year,
        training_end_year=train_prepared.context.training_end_year,
        forecast_origin_year=train_prepared.context.forecast_origin_year,
        missing_years=train_prepared.context.missing_years,
        warnings=warnings,
        errors=[],
    )

    try:
        raw_forecast = selected_forecaster.forecast(
            train_prepared.series_df,
            holdout_year_values,
            context=train_prepared.context,
            options=options,
        )
    except PredictionException:
        raise
    except Exception as exc:  # pragma: no cover - defensive guard for future forecasters
        raise PredictionException(
            PredictionErrorCode.EVALUATION_FAILED,
            str(exc),
            country_code=request.country_code,
            metric_id=request.metric_id,
        ) from exc

    if raw_forecast.warnings:
        warnings = [*diagnostics.warnings, *raw_forecast.warnings]
        diagnostics = PredictionDiagnostics(
            status=PredictionDiagnosticStatus.WARNING,
            country_code=diagnostics.country_code,
            metric_id=diagnostics.metric_id,
            method_requested=diagnostics.method_requested,
            method_used=diagnostics.method_used,
            fallback_used=diagnostics.fallback_used,
            history_observation_count=diagnostics.history_observation_count,
            training_start_year=diagnostics.training_start_year,
            training_end_year=diagnostics.training_end_year,
            forecast_origin_year=diagnostics.forecast_origin_year,
            missing_years=diagnostics.missing_years,
            warnings=warnings,
            errors=diagnostics.errors,
        )

    prediction_run_id = new_prediction_run_id()
    prediction_created_at = prediction_created_at_now()
    actual_vs_predicted_df = _build_actual_vs_predicted_dataframe(
        holdout_df,
        raw_points=[
            {"year": point.year, "predicted_value": point.value, "forecast_horizon": point.horizon}
            for point in raw_forecast.points
        ],
        context_metadata=_context_metadata(train_prepared.context),
        diagnostics=diagnostics,
        prediction_run_id=prediction_run_id,
        prediction_created_at=prediction_created_at,
        scenario_id=request.scenario_id,
    )
    metrics = _compute_metrics(
        actual_vs_predicted_df,
        request=request,
        diagnostics=diagnostics,
    )

    return BacktestResult(
        request=request,
        actual_vs_predicted_df=actual_vs_predicted_df,
        diagnostics=[diagnostics],
        forecaster_info=[raw_forecast.forecaster_info],
        metrics=metrics,
        metadata={
            "prediction_run_id": prediction_run_id,
            "prediction_created_at": prediction_created_at,
            "holdout_years": holdout_year_values,
            "forecast_origin_year": train_prepared.context.forecast_origin_year,
        },
    )


def _validate_backtest_request(request: BacktestRequest, *, options: ForecastOptions) -> None:
    if request.holdout_years <= 0:
        raise PredictionException(
            PredictionErrorCode.INVALID_HORIZON,
            "holdout_years must be greater than zero",
            country_code=request.country_code,
            metric_id=request.metric_id,
            details={"holdout_years": request.holdout_years},
        )

    if request.holdout_years > options.max_horizon_years:
        raise PredictionException(
            PredictionErrorCode.INVALID_HORIZON,
            f"holdout_years must be <= {options.max_horizon_years}",
            country_code=request.country_code,
            metric_id=request.metric_id,
            details={
                "holdout_years": request.holdout_years,
                "max_horizon_years": options.max_horizon_years,
            },
        )

    # Reuse existing method validation semantics.
    probe_request = SingleMetricPredictionRequest(
        country_code=request.country_code,
        metric_id=request.metric_id,
        horizon_years=request.holdout_years,
        method=request.method,
        fallback_method=request.fallback_method,
        history_start_year=request.history_start_year,
        history_end_year=request.history_end_year,
        scenario_id=request.scenario_id,
    )
    from country_compare.prediction.validation import validate_prediction_request

    validate_prediction_request(probe_request, options=options)


def _select_forecaster(
    *,
    requested_method: PredictionMethod,
    fallback_method: PredictionMethod | None,
    train_series: pd.DataFrame,
    diagnostics_context: Any,
    options: ForecastOptions,
):
    requested_forecaster = _resolve_forecaster_or_raise(
        requested_method.value,
        country_code=diagnostics_context.country_code,
        metric_id=diagnostics_context.metric_id,
    )
    selected_forecaster = requested_forecaster
    fallback_used = False
    warnings: list[str] = []

    supported, support_reasons = selected_forecaster.supports(
        train_series,
        context=diagnostics_context,
        options=options,
    )
    if supported:
        return selected_forecaster, fallback_used, warnings

    if fallback_method is not None and fallback_method.value != requested_method.value:
        fallback_forecaster = _resolve_forecaster_or_raise(
            fallback_method.value,
            country_code=diagnostics_context.country_code,
            metric_id=diagnostics_context.metric_id,
        )
        fallback_supported, fallback_reasons = fallback_forecaster.supports(
            train_series,
            context=diagnostics_context,
            options=options,
        )
        if fallback_supported:
            warnings.append(
                f"method '{requested_method.value}' was unsupported for this backtest training series; "
                f"used fallback method '{fallback_method.value}'"
            )
            warnings.extend(support_reasons)
            return fallback_forecaster, True, warnings

        raise PredictionException(
            PredictionErrorCode.INSUFFICIENT_HISTORY,
            "; ".join(fallback_reasons) or "fallback method does not support this training series",
            country_code=diagnostics_context.country_code,
            metric_id=diagnostics_context.metric_id,
            details={
                "method": requested_method.value,
                "method_reasons": support_reasons,
                "fallback_method": fallback_method.value,
                "fallback_reasons": fallback_reasons,
            },
        )

    raise PredictionException(
        PredictionErrorCode.INSUFFICIENT_HISTORY,
        "; ".join(support_reasons) or "requested method does not support this training series",
        country_code=diagnostics_context.country_code,
        metric_id=diagnostics_context.metric_id,
        details={"method": requested_method.value, "reasons": support_reasons},
    )


def _resolve_forecaster_or_raise(method_id: str, *, country_code: str, metric_id: str):
    try:
        return resolve_forecaster(method_id)
    except ForecasterRegistryError as exc:
        raise PredictionException(
            PredictionErrorCode.UNSUPPORTED_METHOD,
            str(exc),
            country_code=country_code,
            metric_id=metric_id,
            details={"method": method_id},
        ) from exc


def _context_metadata(context: Any) -> dict[str, Any]:
    return {
        "country_code": context.country_code,
        "country_name": context.country_name,
        "metric_id": context.metric_id,
        "metric_name": context.metric_name,
        "unit": context.unit,
        "category": context.category,
        "higher_is_better": context.higher_is_better,
        "source_name": context.source_name,
        "source_url": context.source_url,
        "dataset_version": context.dataset_version,
        "region": context.region,
        "income_group": context.income_group,
        "notes": context.notes,
        FORECAST_ORIGIN_YEAR_COLUMN: context.forecast_origin_year,
        TRAINING_START_YEAR_COLUMN: context.training_start_year,
        TRAINING_END_YEAR_COLUMN: context.training_end_year,
    }


def _build_actual_vs_predicted_dataframe(
    holdout_df: pd.DataFrame,
    *,
    raw_points: list[dict[str, Any]],
    context_metadata: dict[str, Any],
    diagnostics: PredictionDiagnostics,
    prediction_run_id: str,
    prediction_created_at: str,
    scenario_id: str,
) -> pd.DataFrame:
    predicted = pd.DataFrame(raw_points)
    predicted[YEAR_COLUMN] = pd.to_numeric(predicted[YEAR_COLUMN], errors="coerce").astype("Int64")
    predicted[PREDICTED_VALUE_COLUMN] = pd.to_numeric(
        predicted[PREDICTED_VALUE_COLUMN],
        errors="coerce",
    ).astype("float64")
    predicted[FORECAST_HORIZON_COLUMN] = pd.to_numeric(
        predicted[FORECAST_HORIZON_COLUMN],
        errors="coerce",
    ).astype("Int64")

    actual = holdout_df.copy(deep=True)
    actual[YEAR_COLUMN] = pd.to_numeric(actual[YEAR_COLUMN], errors="coerce").astype("Int64")
    actual[ACTUAL_VALUE_COLUMN] = pd.to_numeric(actual[VALUE_COLUMN], errors="coerce").astype("float64")

    merged = actual.merge(
        predicted,
        on=YEAR_COLUMN,
        how="left",
        validate="one_to_one",
    )

    merged[ERROR_COLUMN] = merged[PREDICTED_VALUE_COLUMN] - merged[ACTUAL_VALUE_COLUMN]
    merged[ABSOLUTE_ERROR_COLUMN] = merged[ERROR_COLUMN].abs()
    merged[SQUARED_ERROR_COLUMN] = merged[ERROR_COLUMN] ** 2

    nonzero_actual_mask = merged[ACTUAL_VALUE_COLUMN].ne(0) & merged[ACTUAL_VALUE_COLUMN].notna()
    merged[ABSOLUTE_PERCENTAGE_ERROR_COLUMN] = pd.Series(pd.NA, index=merged.index, dtype="Float64")
    merged.loc[nonzero_actual_mask, ABSOLUTE_PERCENTAGE_ERROR_COLUMN] = (
        merged.loc[nonzero_actual_mask, ABSOLUTE_ERROR_COLUMN]
        / merged.loc[nonzero_actual_mask, ACTUAL_VALUE_COLUMN].abs()
    ).astype("float64")

    for column, value in context_metadata.items():
        if column not in merged.columns:
            merged[column] = value

    merged[PREDICTION_METHOD_COLUMN] = diagnostics.method_used
    merged[PREDICTION_RUN_ID_COLUMN] = prediction_run_id
    merged[PREDICTION_CREATED_AT_COLUMN] = prediction_created_at
    merged[SCENARIO_ID_COLUMN] = scenario_id
    merged[DIAGNOSTIC_STATUS_COLUMN] = diagnostics.status.value

    return _order_evaluation_columns(merged)


def _compute_metrics(
    dataframe: pd.DataFrame,
    *,
    request: BacktestRequest,
    diagnostics: PredictionDiagnostics,
) -> dict[str, Any]:
    absolute_error = pd.to_numeric(dataframe[ABSOLUTE_ERROR_COLUMN], errors="coerce")
    squared_error = pd.to_numeric(dataframe[SQUARED_ERROR_COLUMN], errors="coerce")
    actual_values = pd.to_numeric(dataframe[ACTUAL_VALUE_COLUMN], errors="coerce")

    mae = float(absolute_error.mean()) if not absolute_error.dropna().empty else math.nan
    rmse = float(math.sqrt(float(squared_error.mean()))) if not squared_error.dropna().empty else math.nan

    if actual_values.eq(0).any():
        mape = None
    else:
        ape = pd.to_numeric(dataframe[ABSOLUTE_PERCENTAGE_ERROR_COLUMN], errors="coerce")
        mape = float(ape.mean()) if not ape.dropna().empty else None

    years = pd.to_numeric(dataframe[YEAR_COLUMN], errors="coerce").dropna().astype(int)
    return {
        "mae": mae,
        "rmse": rmse,
        "mape": mape,
        "n_train_observations": diagnostics.history_observation_count,
        "n_test_observations": int(len(dataframe.index)),
        "train_start_year": diagnostics.training_start_year,
        "train_end_year": diagnostics.training_end_year,
        "test_start_year": int(years.min()) if not years.empty else None,
        "test_end_year": int(years.max()) if not years.empty else None,
        "method_requested": diagnostics.method_requested,
        "method_used": diagnostics.method_used,
        "fallback_used": diagnostics.fallback_used,
    }


def _order_evaluation_columns(dataframe: pd.DataFrame) -> pd.DataFrame:
    result = dataframe.copy(deep=True)
    for column in EVALUATION_COLUMNS:
        if column not in result.columns:
            result[column] = pd.NA
    extras = [column for column in result.columns if column not in EVALUATION_COLUMNS]
    return result.loc[:, [*EVALUATION_COLUMNS, *extras]].copy(deep=True)


__all__ = [
    "ACTUAL_VALUE_COLUMN",
    "PREDICTED_VALUE_COLUMN",
    "ERROR_COLUMN",
    "ABSOLUTE_ERROR_COLUMN",
    "SQUARED_ERROR_COLUMN",
    "ABSOLUTE_PERCENTAGE_ERROR_COLUMN",
    "EVALUATION_COLUMNS",
    "backtest_series",
]
