from __future__ import annotations

import pandas as pd

from country_compare.data.contract import (
    COUNTRY_CODE_COLUMN,
    COUNTRY_NAME_COLUMN,
    METRIC_ID_COLUMN,
    METRIC_NAME_COLUMN,
    UNIT_COLUMN,
    VALUE_COLUMN,
    YEAR_COLUMN,
)
from country_compare.prediction.models import PredictionResult
from country_compare.prediction.output import (
    CONFIDENCE_LOWER_COLUMN,
    CONFIDENCE_UPPER_COLUMN,
    DIAGNOSTIC_STATUS_COLUMN,
    FORECAST_HORIZON_COLUMN,
    FORECAST_ORIGIN_YEAR_COLUMN,
    PREDICTION_METHOD_COLUMN,
    ROW_TYPE_COLUMN,
    SCENARIO_ID_COLUMN,
)

SERIES_LABEL_COLUMN = "series_label"
OVERLAY_SERIES_LABEL_COLUMN = "overlay_series_label"
SERIES_GROUP_COLUMN = "series_group"
FORECAST_YEAR_COLUMN = "forecast_year"
PREDICTED_VALUE_COLUMN = "predicted_value"

LINE_CHART_COLUMNS: tuple[str, ...] = (
    COUNTRY_CODE_COLUMN,
    COUNTRY_NAME_COLUMN,
    METRIC_ID_COLUMN,
    METRIC_NAME_COLUMN,
    YEAR_COLUMN,
    VALUE_COLUMN,
    ROW_TYPE_COLUMN,
    SERIES_LABEL_COLUMN,
    OVERLAY_SERIES_LABEL_COLUMN,
    SERIES_GROUP_COLUMN,
    PREDICTION_METHOD_COLUMN,
    FORECAST_ORIGIN_YEAR_COLUMN,
    FORECAST_HORIZON_COLUMN,
    CONFIDENCE_LOWER_COLUMN,
    CONFIDENCE_UPPER_COLUMN,
    UNIT_COLUMN,
    SCENARIO_ID_COLUMN,
    DIAGNOSTIC_STATUS_COLUMN,
)

FORECAST_TABLE_COLUMNS: tuple[str, ...] = (
    COUNTRY_CODE_COLUMN,
    COUNTRY_NAME_COLUMN,
    METRIC_ID_COLUMN,
    METRIC_NAME_COLUMN,
    FORECAST_YEAR_COLUMN,
    FORECAST_HORIZON_COLUMN,
    PREDICTED_VALUE_COLUMN,
    UNIT_COLUMN,
    PREDICTION_METHOD_COLUMN,
    FORECAST_ORIGIN_YEAR_COLUMN,
    CONFIDENCE_LOWER_COLUMN,
    CONFIDENCE_UPPER_COLUMN,
    SCENARIO_ID_COLUMN,
    DIAGNOSTIC_STATUS_COLUMN,
)


def build_line_chart_dataframe(result: PredictionResult) -> pd.DataFrame:
    """
    Build a renderer-neutral long dataframe for prediction line charts.
    """
    dataframe = _copy_result_dataframe(result, "combined_df")
    dataframe = _with_visualization_labels(dataframe, split_actual_forecast=True)
    dataframe = _sort_visualization_dataframe(dataframe)
    return _select_preferred_columns(dataframe, LINE_CHART_COLUMNS)


def build_actual_vs_predicted_dataframe(result: PredictionResult) -> pd.DataFrame:
    """
    Build a long actual-vs-predicted overlay dataframe.

    Unlike build_line_chart_dataframe, this uses the same series_label for actual
    and predicted rows from the same country/metric pair. Renderers can use
    row_type for styling.
    """
    dataframe = _copy_result_dataframe(result, "combined_df")
    dataframe = _with_visualization_labels(dataframe, split_actual_forecast=False)
    dataframe = _sort_visualization_dataframe(dataframe)
    return _select_preferred_columns(dataframe, LINE_CHART_COLUMNS)


def build_forecast_table_dataframe(result: PredictionResult) -> pd.DataFrame:
    """
    Build a forecast-only display table from result.forecast_df.
    """
    dataframe = _copy_result_dataframe(result, "forecast_df")
    if ROW_TYPE_COLUMN in dataframe.columns:
        dataframe = dataframe.loc[
            dataframe[ROW_TYPE_COLUMN].astype("string").eq("predicted")
        ].copy()

    if YEAR_COLUMN in dataframe.columns:
        dataframe[FORECAST_YEAR_COLUMN] = pd.to_numeric(
            dataframe[YEAR_COLUMN],
            errors="coerce",
        ).astype("Int64")
    else:
        dataframe[FORECAST_YEAR_COLUMN] = pd.Series(
            index=dataframe.index, dtype="Int64"
        )

    if VALUE_COLUMN in dataframe.columns:
        dataframe[PREDICTED_VALUE_COLUMN] = pd.to_numeric(
            dataframe[VALUE_COLUMN],
            errors="coerce",
        ).astype("float64")
    else:
        dataframe[PREDICTED_VALUE_COLUMN] = pd.Series(
            index=dataframe.index, dtype="float64"
        )

    dataframe = _sort_visualization_dataframe(dataframe)
    return _select_preferred_columns(dataframe, FORECAST_TABLE_COLUMNS)


def _copy_result_dataframe(
    result: PredictionResult, attribute_name: str
) -> pd.DataFrame:
    dataframe = getattr(result, attribute_name, None)
    if dataframe is None:
        raise ValueError(
            f"prediction result is missing dataframe attribute: {attribute_name}"
        )
    if not isinstance(dataframe, pd.DataFrame):
        raise TypeError(
            f"prediction result attribute {attribute_name!r} must be a pandas DataFrame"
        )
    return dataframe.copy(deep=True)


def _with_visualization_labels(
    dataframe: pd.DataFrame,
    *,
    split_actual_forecast: bool,
) -> pd.DataFrame:
    result = dataframe.copy(deep=True)
    _ensure_columns(result, LINE_CHART_COLUMNS)
    if result.empty:
        result[SERIES_LABEL_COLUMN] = pd.Series(index=result.index, dtype="string")
        result[OVERLAY_SERIES_LABEL_COLUMN] = pd.Series(
            index=result.index, dtype="string"
        )
        result[SERIES_GROUP_COLUMN] = pd.Series(index=result.index, dtype="string")
        return result

    country_count = _distinct_count(result, COUNTRY_CODE_COLUMN)
    metric_count = _distinct_count(result, METRIC_ID_COLUMN)

    country_labels = result.apply(_country_display_label, axis=1)
    metric_labels = result.apply(_metric_display_label, axis=1)
    row_type_labels = result[ROW_TYPE_COLUMN].map(_row_type_display_label)

    if country_count > 1 and metric_count > 1:
        base_labels = country_labels + " — " + metric_labels
    elif metric_count > 1:
        base_labels = metric_labels
    else:
        base_labels = country_labels

    result[OVERLAY_SERIES_LABEL_COLUMN] = base_labels
    if split_actual_forecast:
        result[SERIES_LABEL_COLUMN] = base_labels + " " + row_type_labels
    else:
        result[SERIES_LABEL_COLUMN] = base_labels

    result[SERIES_GROUP_COLUMN] = (
        result[COUNTRY_CODE_COLUMN].astype("string").fillna("")
        + "|"
        + result[METRIC_ID_COLUMN].astype("string").fillna("")
        + "|"
        + result[ROW_TYPE_COLUMN].astype("string").fillna("")
    )
    return result


def _country_display_label(row: pd.Series) -> str:
    country_name = _clean_label_value(row.get(COUNTRY_NAME_COLUMN))
    if country_name:
        return country_name

    country_code = _clean_label_value(row.get(COUNTRY_CODE_COLUMN))
    if country_code:
        return country_code

    return "Unknown country"


def _metric_display_label(row: pd.Series) -> str:
    metric_name = _clean_label_value(row.get(METRIC_NAME_COLUMN))
    if metric_name:
        return metric_name

    metric_id = _clean_label_value(row.get(METRIC_ID_COLUMN))
    if metric_id:
        return metric_id

    return "Unknown metric"


def _row_type_display_label(value: object) -> str:
    text = _clean_label_value(value).lower()
    if text == "predicted":
        return "forecast"
    if text == "actual":
        return "actual"
    if text:
        return text
    return "series"


def _clean_label_value(value: object) -> str:
    if value is None or pd.isna(value):
        return ""
    return str(value).strip()


def _distinct_count(dataframe: pd.DataFrame, column: str) -> int:
    if column not in dataframe.columns or dataframe.empty:
        return 0
    return int(dataframe[column].dropna().astype("string").nunique())


def _ensure_columns(dataframe: pd.DataFrame, columns: tuple[str, ...]) -> None:
    for column in columns:
        if column in dataframe.columns:
            continue
        if column in {
            YEAR_COLUMN,
            FORECAST_HORIZON_COLUMN,
            FORECAST_ORIGIN_YEAR_COLUMN,
        }:
            dataframe[column] = pd.Series(index=dataframe.index, dtype="Int64")
        elif column in {VALUE_COLUMN, CONFIDENCE_LOWER_COLUMN, CONFIDENCE_UPPER_COLUMN}:
            dataframe[column] = pd.Series(index=dataframe.index, dtype="float64")
        else:
            dataframe[column] = pd.NA


def _sort_visualization_dataframe(dataframe: pd.DataFrame) -> pd.DataFrame:
    if dataframe.empty:
        return dataframe.copy(deep=True)

    result = dataframe.copy(deep=True)
    if (
        SERIES_GROUP_COLUMN not in result.columns
        or result[SERIES_GROUP_COLUMN].isna().all()
    ):
        return result.reset_index(drop=True)

    result["_series_sort_order"] = result.groupby(
        SERIES_GROUP_COLUMN, sort=False
    ).ngroup()
    result["_row_type_sort_order"] = (
        result.get(ROW_TYPE_COLUMN, pd.Series(index=result.index, dtype="string"))
        .astype("string")
        .map({"actual": 0, "predicted": 1})
        .fillna(2)
        .astype(int)
    )

    sort_columns = [
        column
        for column in (
            "_series_sort_order",
            YEAR_COLUMN,
            "_row_type_sort_order",
            FORECAST_HORIZON_COLUMN,
        )
        if column in result.columns
    ]
    result = result.sort_values(
        by=sort_columns,
        ascending=[True] * len(sort_columns),
        kind="mergesort",
        na_position="last",
    ).drop(columns=["_series_sort_order", "_row_type_sort_order"])
    return result.reset_index(drop=True)


def _select_preferred_columns(
    dataframe: pd.DataFrame,
    preferred_columns: tuple[str, ...],
) -> pd.DataFrame:
    result = dataframe.copy(deep=True)
    _ensure_columns(result, preferred_columns)
    extras = [column for column in result.columns if column not in preferred_columns]
    return result.loc[:, [*preferred_columns, *extras]].copy(deep=True)


__all__ = [
    "LINE_CHART_COLUMNS",
    "FORECAST_TABLE_COLUMNS",
    "SERIES_LABEL_COLUMN",
    "OVERLAY_SERIES_LABEL_COLUMN",
    "SERIES_GROUP_COLUMN",
    "FORECAST_YEAR_COLUMN",
    "PREDICTED_VALUE_COLUMN",
    "build_line_chart_dataframe",
    "build_actual_vs_predicted_dataframe",
    "build_forecast_table_dataframe",
]
