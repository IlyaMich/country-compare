from __future__ import annotations

import pandas as pd

from country_compare.prediction.errors import PredictionErrorCode, PredictionException
from country_compare.prediction.models import (
    ForecastOptions,
    PredictionDiagnosticStatus,
    PredictionDiagnostics,
    PredictionError,
    PredictionResult,
    SingleMetricPredictionRequest,
)
from country_compare.prediction.output import (
    build_combined_dataframe,
    build_comparison_ready_dataframe,
    build_forecast_dataframe,
    new_prediction_run_id,
    prediction_created_at_now,
)
from country_compare.prediction.registry import ForecasterRegistryError, resolve_forecaster
from country_compare.prediction.timeseries import prepare_metric_time_series
from country_compare.prediction.validation import (
    resolve_fallback_method,
    resolve_requested_method,
    validate_prediction_request,
)


def predict_single_metric(
    canonical_df: pd.DataFrame,
    request: SingleMetricPredictionRequest,
    *,
    options: ForecastOptions | None = None,
) -> PredictionResult:
    """
    Forecast one country + one metric from a canonical dataframe.

    This is the Phase A/B public entrypoint: it validates the request, prepares a
    single annual series, applies a registered forecaster, and returns forecast,
    combined actual+forecast, and comparison-ready dataframes.
    """
    if not isinstance(request, SingleMetricPredictionRequest):
        request = SingleMetricPredictionRequest.model_validate(request)

    options = options or ForecastOptions(scenario_id=request.scenario_id)
    validate_prediction_request(request, options=options)

    prepared = prepare_metric_time_series(canonical_df, request)
    requested_method = resolve_requested_method(request)
    fallback_method = resolve_fallback_method(request)

    requested_forecaster = _resolve_forecaster_or_raise(
        requested_method.value,
        country_code=request.country_code,
        metric_id=request.metric_id,
    )
    selected_forecaster = requested_forecaster
    fallback_used = False
    warnings = list(prepared.warnings)

    supported, support_reasons = selected_forecaster.supports(
        prepared.series_df,
        context=prepared.context,
        options=options,
    )
    if not supported:
        if fallback_method is not None and fallback_method.value != requested_method.value:
            fallback_forecaster = _resolve_forecaster_or_raise(
                fallback_method.value,
                country_code=request.country_code,
                metric_id=request.metric_id,
            )
            fallback_supported, fallback_reasons = fallback_forecaster.supports(
                prepared.series_df,
                context=prepared.context,
                options=options,
            )
            if fallback_supported:
                selected_forecaster = fallback_forecaster
                fallback_used = True
                warnings.append(
                    f"method '{requested_method.value}' was unsupported for this series; "
                    f"used fallback method '{fallback_method.value}'"
                )
                warnings.extend(support_reasons)
            else:
                raise PredictionException(
                    PredictionErrorCode.INSUFFICIENT_HISTORY,
                    "; ".join(fallback_reasons) or "fallback method does not support this series",
                    country_code=request.country_code,
                    metric_id=request.metric_id,
                    details={
                        "method": requested_method.value,
                        "method_reasons": support_reasons,
                        "fallback_method": fallback_method.value,
                        "fallback_reasons": fallback_reasons,
                    },
                )
        else:
            raise PredictionException(
                PredictionErrorCode.INSUFFICIENT_HISTORY,
                "; ".join(support_reasons) or "requested method does not support this series",
                country_code=request.country_code,
                metric_id=request.metric_id,
                details={"method": requested_method.value, "reasons": support_reasons},
            )

    status = PredictionDiagnosticStatus.WARNING if warnings else PredictionDiagnosticStatus.OK
    diagnostics = PredictionDiagnostics(
        status=status,
        country_code=request.country_code,
        metric_id=request.metric_id,
        method_requested=requested_method.value,
        method_used=selected_forecaster.method_id,
        fallback_used=fallback_used,
        history_observation_count=prepared.context.history_observation_count,
        training_start_year=prepared.context.training_start_year,
        training_end_year=prepared.context.training_end_year,
        forecast_origin_year=prepared.context.forecast_origin_year,
        missing_years=prepared.context.missing_years,
        warnings=warnings,
        errors=[],
    )

    if request.fail_on_warning and diagnostics.status == PredictionDiagnosticStatus.WARNING:
        raise PredictionException(
            PredictionErrorCode.UNSUPPORTED_SERIES_SHAPE,
            "prediction produced warnings and fail_on_warning=True",
            country_code=request.country_code,
            metric_id=request.metric_id,
            details={"warnings": warnings},
        )

    try:
        raw_forecast = selected_forecaster.forecast(
            prepared.series_df,
            prepared.future_years,
            context=prepared.context,
            options=options,
        )
    except PredictionException:
        raise
    except Exception as exc:  # pragma: no cover - defensive guard for future forecasters
        raise PredictionException(
            PredictionErrorCode.FORECASTING_FAILED,
            str(exc),
            country_code=request.country_code,
            metric_id=request.metric_id,
        ) from exc

    if raw_forecast.warnings:
        all_warnings = [*diagnostics.warnings, *raw_forecast.warnings]
        diagnostics = diagnostics.model_copy(
            update={"status": PredictionDiagnosticStatus.WARNING, "warnings": all_warnings}
        )

    prediction_run_id = new_prediction_run_id()
    prediction_created_at = prediction_created_at_now()
    forecast_df = build_forecast_dataframe(
        raw_forecast,
        context=prepared.context,
        diagnostics=diagnostics,
        prediction_run_id=prediction_run_id,
        prediction_created_at=prediction_created_at,
        scenario_id=request.scenario_id,
    )
    combined_df = build_combined_dataframe(
        prepared.series_df if request.include_actuals else prepared.series_df.iloc[0:0].copy(),
        forecast_df,
        context=prepared.context,
        diagnostics=diagnostics,
        method_id=selected_forecaster.method_id,
        prediction_run_id=prediction_run_id,
        prediction_created_at=prediction_created_at,
        scenario_id=request.scenario_id,
    )
    comparison_ready_df = build_comparison_ready_dataframe(forecast_df)

    return PredictionResult(
        request=request,
        forecast_df=forecast_df,
        combined_df=combined_df,
        comparison_ready_df=comparison_ready_df,
        diagnostics=[diagnostics],
        forecaster_info=[raw_forecast.forecaster_info],
        metadata={
            "prediction_run_id": prediction_run_id,
            "prediction_created_at": prediction_created_at,
            "method_requested": requested_method.value,
            "method_used": selected_forecaster.method_id,
            "fallback_used": fallback_used,
        },
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


__all__ = ["predict_single_metric"]
