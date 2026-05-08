from __future__ import annotations

from collections.abc import Sequence
from dataclasses import asdict, is_dataclass
from enum import Enum
from typing import Any, cast

import pandas as pd

from country_compare.data.contract import (
    COUNTRY_CODE_COLUMN,
    METRIC_ID_COLUMN,
    YEAR_COLUMN,
)
from country_compare.prediction.errors import PredictionException
from country_compare.prediction.models import (
    BacktestResult,
    ForecasterInfo,
    PredictedComparisonResult,
    PredictionDiagnostics,
    PredictionResult,
)
from country_compare.prediction.output import (
    FORECAST_HORIZON_COLUMN,
    PREDICTION_METHOD_COLUMN,
)
from country_compare.prediction.registry import list_forecasters, resolve_forecaster


def list_available_prediction_methods() -> list[dict[str, Any]]:
    """Return a UI/API-friendly catalog of currently registered forecasters."""
    methods: list[dict[str, Any]] = []

    for method_id in list_forecasters():
        forecaster = resolve_forecaster(method_id)
        info = forecaster.info()
        methods.append(build_forecaster_info_summary(info))

    return methods


def list_forecast_years(
    result: PredictionResult | PredictedComparisonResult,
) -> list[int]:
    prediction_result = _as_prediction_result(result)
    return _unique_ints(prediction_result.forecast_df, YEAR_COLUMN)


def list_forecast_horizons(
    result: PredictionResult | PredictedComparisonResult,
) -> list[int]:
    prediction_result = _as_prediction_result(result)
    return _unique_ints(prediction_result.forecast_df, FORECAST_HORIZON_COLUMN)


def build_prediction_result_summary(result: PredictionResult) -> dict[str, Any]:
    """Build a stable, serializable summary without serializing full DataFrames."""
    forecast_years = list_forecast_years(result)
    forecast_horizons = list_forecast_horizons(result)

    return {
        "result_type": "prediction",
        "request": _request_summary(result.request),
        "forecast": _dataframe_summary(result.forecast_df),
        "combined": _dataframe_summary(result.combined_df),
        "comparison_ready": _dataframe_summary(result.comparison_ready_df),
        "forecast_years": forecast_years,
        "forecast_horizons": forecast_horizons,
        "countries": _unique_strings(result.forecast_df, COUNTRY_CODE_COLUMN),
        "metrics": _unique_strings(result.forecast_df, METRIC_ID_COLUMN),
        "methods_used": _unique_strings(result.forecast_df, PREDICTION_METHOD_COLUMN),
        "metadata": _json_safe_mapping(result.metadata),
        "diagnostics": build_prediction_diagnostics_collection_summary(
            result.diagnostics
        ),
        "forecasters": [
            build_forecaster_info_summary(info) for info in result.forecaster_info
        ],
    }


def build_predicted_comparison_result_summary(
    result: PredictedComparisonResult,
) -> dict[str, Any]:
    return {
        "result_type": "predicted_comparison",
        "selected_forecast_year": result.selected_forecast_year,
        "selected_forecast_horizon": result.selected_forecast_horizon,
        "comparison": _dataframe_summary(result.comparison_df),
        "metadata": _json_safe_mapping(result.metadata),
        "prediction": build_prediction_result_summary(result.prediction_result),
        "diagnostics": build_prediction_diagnostics_collection_summary(
            result.diagnostics
        ),
    }


def build_backtest_result_summary(result: BacktestResult) -> dict[str, Any]:
    return {
        "result_type": "backtest",
        "request": _request_summary(result.request),
        "actual_vs_predicted": _dataframe_summary(result.actual_vs_predicted_df),
        "metrics": _json_safe_mapping(result.metrics),
        "metadata": _json_safe_mapping(result.metadata),
        "diagnostics": build_prediction_diagnostics_collection_summary(
            result.diagnostics
        ),
        "forecasters": [
            build_forecaster_info_summary(info) for info in result.forecaster_info
        ],
    }


def build_prediction_diagnostics_collection_summary(
    diagnostics: Sequence[PredictionDiagnostics],
) -> dict[str, Any]:
    status_counts: dict[str, int] = {}
    warnings: list[str] = []
    errors: list[dict[str, Any]] = []

    for diagnostic in diagnostics:
        status = _enum_value(diagnostic.status)
        status_counts[status] = status_counts.get(status, 0) + 1
        warnings.extend(str(message) for message in diagnostic.warnings)
        errors.extend(_prediction_error_summary(error) for error in diagnostic.errors)

    return {
        "count": len(diagnostics),
        "status_counts": status_counts,
        "warnings": warnings,
        "errors": errors,
        "items": [
            build_prediction_diagnostic_summary(diagnostic)
            for diagnostic in diagnostics
        ],
    }


def build_prediction_diagnostic_summary(
    diagnostic: PredictionDiagnostics,
) -> dict[str, Any]:
    return {
        "status": _enum_value(diagnostic.status),
        "country_code": diagnostic.country_code,
        "metric_id": diagnostic.metric_id,
        "method_requested": diagnostic.method_requested,
        "method_used": diagnostic.method_used,
        "fallback_used": diagnostic.fallback_used,
        "history_observation_count": diagnostic.history_observation_count,
        "training_start_year": diagnostic.training_start_year,
        "training_end_year": diagnostic.training_end_year,
        "forecast_origin_year": diagnostic.forecast_origin_year,
        "missing_years": list(diagnostic.missing_years),
        "warnings": list(diagnostic.warnings),
        "errors": [_prediction_error_summary(error) for error in diagnostic.errors],
        "messages": list(diagnostic.messages),
    }


def build_forecaster_info_summary(info: ForecasterInfo) -> dict[str, Any]:
    return {
        "method_id": info.method_id,
        "display_name": info.display_name,
        "description": info.description,
        "metadata": _json_safe_mapping(info.metadata),
    }


def prediction_exception_to_dict(exc: PredictionException) -> dict[str, Any]:
    return {
        "code": exc.code.value,
        "message": exc.message,
        "country_code": exc.country_code,
        "metric_id": exc.metric_id,
        "year": exc.year,
        "details": _json_safe_mapping(exc.details),
    }


def _as_prediction_result(
    result: PredictionResult | PredictedComparisonResult,
) -> PredictionResult:
    if isinstance(result, PredictedComparisonResult):
        return result.prediction_result
    return result


def _dataframe_summary(dataframe: pd.DataFrame) -> dict[str, Any]:
    return {
        "row_count": int(len(dataframe.index)),
        "column_count": int(len(dataframe.columns)),
        "columns": [str(column) for column in dataframe.columns.tolist()],
    }


def _request_summary(request: Any) -> dict[str, Any]:
    if is_dataclass(request) and not isinstance(request, type):
        return _json_safe_mapping(asdict(cast(Any, request)))
    public_dict = getattr(request, "__dict__", None)
    if isinstance(public_dict, dict):
        return _json_safe_mapping(
            {
                key: value
                for key, value in public_dict.items()
                if not str(key).startswith("_")
            }
        )
    return {"value": str(request)}


def _unique_strings(dataframe: pd.DataFrame, column: str) -> list[str]:
    if column not in dataframe.columns:
        return []
    values = dataframe[column].dropna().astype("string").tolist()
    return sorted({str(value) for value in values})


def _unique_ints(dataframe: pd.DataFrame, column: str) -> list[int]:
    if column not in dataframe.columns:
        return []
    values = pd.to_numeric(dataframe[column], errors="coerce").dropna().astype(int)
    return sorted({int(value) for value in values.tolist()})


def _prediction_error_summary(error: Any) -> dict[str, Any]:
    return {
        "code": _enum_value(getattr(error, "code", None)),
        "message": getattr(error, "message", str(error)),
        "severity": getattr(error, "severity", None),
        "country_code": getattr(error, "country_code", None),
        "metric_id": getattr(error, "metric_id", None),
        "year": getattr(error, "year", None),
        "details": _json_safe_mapping(getattr(error, "details", {}) or {}),
    }


def _json_safe_mapping(mapping: dict[str, Any]) -> dict[str, Any]:
    return {
        str(key): _json_safe_value(value) for key, value in dict(mapping or {}).items()
    }


def _json_safe_value(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, (str, int, bool)):
        return value
    if isinstance(value, float):
        return None if pd.isna(value) else value
    if value is pd.NA or value is pd.NaT:
        return None
    if isinstance(value, pd.Timestamp):
        return None if pd.isna(value) else value.isoformat()
    if isinstance(value, dict):
        return _json_safe_mapping(value)
    if isinstance(value, (list, tuple, set)):
        return [_json_safe_value(item) for item in value]
    if is_dataclass(value) and not isinstance(value, type):
        return _json_safe_mapping(asdict(cast(Any, value)))
    return str(value)


def _enum_value(value: Any) -> Any:
    return value.value if isinstance(value, Enum) else value
