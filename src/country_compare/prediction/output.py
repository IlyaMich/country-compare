from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pandas as pd

from country_compare.data.contract import ALL_COLUMNS, REQUIRED_COLUMNS
from country_compare.prediction.models import (
    ForecastContext,
    PredictionDiagnostics,
    RawForecastResult,
)

ROW_TYPE_COLUMN = "row_type"
IS_PREDICTED_COLUMN = "is_predicted"
FORECAST_HORIZON_COLUMN = "forecast_horizon"
FORECAST_ORIGIN_YEAR_COLUMN = "forecast_origin_year"
PREDICTION_METHOD_COLUMN = "prediction_method"
PREDICTION_RUN_ID_COLUMN = "prediction_run_id"
PREDICTION_CREATED_AT_COLUMN = "prediction_created_at"
TRAINING_START_YEAR_COLUMN = "training_start_year"
TRAINING_END_YEAR_COLUMN = "training_end_year"
HISTORY_OBSERVATION_COUNT_COLUMN = "history_observation_count"
CONFIDENCE_LOWER_COLUMN = "confidence_lower"
CONFIDENCE_UPPER_COLUMN = "confidence_upper"
DIAGNOSTIC_STATUS_COLUMN = "diagnostic_status"
DIAGNOSTIC_MESSAGES_COLUMN = "diagnostic_messages"
SCENARIO_ID_COLUMN = "scenario_id"

PREDICTION_METADATA_COLUMNS: tuple[str, ...] = (
    ROW_TYPE_COLUMN,
    IS_PREDICTED_COLUMN,
    FORECAST_HORIZON_COLUMN,
    FORECAST_ORIGIN_YEAR_COLUMN,
    PREDICTION_METHOD_COLUMN,
    PREDICTION_RUN_ID_COLUMN,
    PREDICTION_CREATED_AT_COLUMN,
    TRAINING_START_YEAR_COLUMN,
    TRAINING_END_YEAR_COLUMN,
    HISTORY_OBSERVATION_COUNT_COLUMN,
    CONFIDENCE_LOWER_COLUMN,
    CONFIDENCE_UPPER_COLUMN,
    DIAGNOSTIC_STATUS_COLUMN,
    DIAGNOSTIC_MESSAGES_COLUMN,
    SCENARIO_ID_COLUMN,
)


def new_prediction_run_id() -> str:
    return str(uuid4())


def prediction_created_at_now() -> str:
    return datetime.now(tz=UTC).isoformat()


def build_forecast_dataframe(
    raw_forecast: RawForecastResult,
    *,
    context: ForecastContext,
    diagnostics: PredictionDiagnostics,
    prediction_run_id: str,
    prediction_created_at: str,
    scenario_id: str = "baseline",
) -> pd.DataFrame:
    rows = []
    diagnostic_messages = _diagnostic_messages_as_text(diagnostics)
    for point in raw_forecast.points:
        rows.append(
            {
                "country_code": context.country_code,
                "country_name": context.country_name,
                "metric_id": context.metric_id,
                "metric_name": context.metric_name,
                "value": float(point.value),
                "year": int(point.year),
                "unit": context.unit,
                "source_name": context.source_name,
                "source_url": context.source_url,
                "higher_is_better": context.higher_is_better,
                "category": context.category,
                "dataset_version": context.dataset_version,
                "region": context.region,
                "income_group": context.income_group,
                "notes": context.notes,
                ROW_TYPE_COLUMN: "predicted",
                IS_PREDICTED_COLUMN: True,
                FORECAST_HORIZON_COLUMN: int(point.horizon),
                FORECAST_ORIGIN_YEAR_COLUMN: context.forecast_origin_year,
                PREDICTION_METHOD_COLUMN: raw_forecast.method_id,
                PREDICTION_RUN_ID_COLUMN: prediction_run_id,
                PREDICTION_CREATED_AT_COLUMN: prediction_created_at,
                TRAINING_START_YEAR_COLUMN: context.training_start_year,
                TRAINING_END_YEAR_COLUMN: context.training_end_year,
                HISTORY_OBSERVATION_COUNT_COLUMN: context.history_observation_count,
                CONFIDENCE_LOWER_COLUMN: pd.NA,
                CONFIDENCE_UPPER_COLUMN: pd.NA,
                DIAGNOSTIC_STATUS_COLUMN: diagnostics.status.value,
                DIAGNOSTIC_MESSAGES_COLUMN: diagnostic_messages,
                SCENARIO_ID_COLUMN: scenario_id,
            }
        )

    dataframe = pd.DataFrame(rows)
    return order_prediction_columns(dataframe)


def build_combined_dataframe(
    actual_series_df: pd.DataFrame,
    forecast_df: pd.DataFrame,
    *,
    context: ForecastContext,
    diagnostics: PredictionDiagnostics,
    method_id: str,
    prediction_run_id: str,
    prediction_created_at: str,
    scenario_id: str = "baseline",
) -> pd.DataFrame:
    actual = actual_series_df.copy(deep=True)
    diagnostic_messages = _diagnostic_messages_as_text(diagnostics)

    actual[ROW_TYPE_COLUMN] = "actual"
    actual[IS_PREDICTED_COLUMN] = False
    actual[FORECAST_HORIZON_COLUMN] = 0
    actual[FORECAST_ORIGIN_YEAR_COLUMN] = context.forecast_origin_year
    actual[PREDICTION_METHOD_COLUMN] = method_id
    actual[PREDICTION_RUN_ID_COLUMN] = prediction_run_id
    actual[PREDICTION_CREATED_AT_COLUMN] = prediction_created_at
    actual[TRAINING_START_YEAR_COLUMN] = context.training_start_year
    actual[TRAINING_END_YEAR_COLUMN] = context.training_end_year
    actual[HISTORY_OBSERVATION_COUNT_COLUMN] = context.history_observation_count
    actual[CONFIDENCE_LOWER_COLUMN] = pd.NA
    actual[CONFIDENCE_UPPER_COLUMN] = pd.NA
    actual[DIAGNOSTIC_STATUS_COLUMN] = diagnostics.status.value
    actual[DIAGNOSTIC_MESSAGES_COLUMN] = diagnostic_messages
    actual[SCENARIO_ID_COLUMN] = scenario_id

    combined = pd.concat([actual, forecast_df], ignore_index=True, sort=False)
    return order_prediction_columns(combined)


def build_comparison_ready_dataframe(forecast_df: pd.DataFrame) -> pd.DataFrame:
    """Return canonical-like predicted rows suitable for existing comparison functions."""
    missing = [
        column for column in REQUIRED_COLUMNS if column not in forecast_df.columns
    ]
    if missing:
        raise ValueError(
            f"forecast dataframe is missing required canonical columns: {missing}"
        )
    return order_prediction_columns(forecast_df.copy(deep=True))


def order_prediction_columns(dataframe: pd.DataFrame) -> pd.DataFrame:
    result = dataframe.copy(deep=True)
    for column in ALL_COLUMNS:
        if column not in result.columns:
            result[column] = pd.NA
    for column in PREDICTION_METADATA_COLUMNS:
        if column not in result.columns:
            result[column] = pd.NA

    preferred = [*ALL_COLUMNS, *PREDICTION_METADATA_COLUMNS]
    extras = [column for column in result.columns if column not in preferred]
    return result.loc[:, [*preferred, *extras]].copy(deep=True)


def _diagnostic_messages_as_text(diagnostics: PredictionDiagnostics) -> str:
    return "; ".join(diagnostics.messages)


__all__ = [
    "PREDICTION_METADATA_COLUMNS",
    "new_prediction_run_id",
    "prediction_created_at_now",
    "build_forecast_dataframe",
    "build_combined_dataframe",
    "build_comparison_ready_dataframe",
    "order_prediction_columns",
]
