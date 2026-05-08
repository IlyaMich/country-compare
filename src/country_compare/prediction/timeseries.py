from __future__ import annotations

from typing import Any

import pandas as pd

from country_compare.prediction.models import (
    ForecastContext,
    PreparedTimeSeries,
    SingleMetricPredictionRequest,
)
from country_compare.prediction.validation import (
    COUNTRY_CODE_COLUMN,
    METRIC_ID_COLUMN,
    VALUE_COLUMN,
    YEAR_COLUMN,
    identify_missing_internal_years,
    validate_canonical_prediction_input,
    validate_country_metric_presence,
    validate_non_empty_series,
    validate_numeric_series_values,
    validate_series_uniqueness,
)

_METADATA_COLUMNS: tuple[str, ...] = (
    "country_name",
    "metric_name",
    "unit",
    "category",
    "higher_is_better",
    "source_name",
    "source_url",
    "dataset_version",
    "region",
    "income_group",
    "notes",
)


def prepare_metric_time_series(
    canonical_df: pd.DataFrame,
    request: SingleMetricPredictionRequest,
) -> PreparedTimeSeries:
    """Prepare one annual country/metric series from canonical dataframe rows."""
    validate_canonical_prediction_input(canonical_df)
    validate_country_metric_presence(
        canonical_df,
        country_code=request.country_code,
        metric_id=request.metric_id,
    )

    working = canonical_df.copy(deep=True)
    country_series = working[COUNTRY_CODE_COLUMN].astype("string").str.upper()
    metric_series = working[METRIC_ID_COLUMN].astype("string")

    series_df = working.loc[
        country_series.eq(request.country_code.upper())
        & metric_series.eq(request.metric_id)
    ].copy()

    if request.history_start_year is not None:
        series_df = series_df.loc[
            pd.to_numeric(series_df[YEAR_COLUMN], errors="coerce").ge(
                int(request.history_start_year)
            )
        ].copy()
    if request.history_end_year is not None:
        series_df = series_df.loc[
            pd.to_numeric(series_df[YEAR_COLUMN], errors="coerce").le(
                int(request.history_end_year)
            )
        ].copy()

    validate_non_empty_series(
        series_df,
        country_code=request.country_code,
        metric_id=request.metric_id,
    )

    series_df[YEAR_COLUMN] = pd.to_numeric(
        series_df[YEAR_COLUMN], errors="coerce"
    ).astype("Int64")
    validate_series_uniqueness(
        series_df,
        country_code=request.country_code,
        metric_id=request.metric_id,
    )

    series_df[VALUE_COLUMN] = validate_numeric_series_values(
        series_df,
        country_code=request.country_code,
        metric_id=request.metric_id,
    )
    series_df = series_df.sort_values(by=YEAR_COLUMN, kind="mergesort").reset_index(
        drop=True
    )

    years = [int(year) for year in series_df[YEAR_COLUMN].dropna().tolist()]
    missing_years = identify_missing_internal_years(years)
    warnings: list[str] = []
    if missing_years:
        warnings.append(
            "series has missing internal years: "
            + ", ".join(str(year) for year in missing_years)
        )

    latest_row = series_df.iloc[-1]
    origin_year = int(latest_row[YEAR_COLUMN])
    future_years = [
        origin_year + step for step in range(1, int(request.horizon_years) + 1)
    ]
    metadata = _extract_context_metadata(latest_row, series_df=series_df)

    return PreparedTimeSeries(
        series_df=series_df.copy(deep=True),
        future_years=future_years,
        context=ForecastContext(
            country_code=request.country_code.upper(),
            metric_id=request.metric_id,
            forecast_origin_year=origin_year,
            horizon_years=int(request.horizon_years),
            history_observation_count=int(len(series_df.index)),
            country_name=_optional_str(metadata.get("country_name")),
            metric_name=_optional_str(metadata.get("metric_name")),
            unit=_optional_str(metadata.get("unit")),
            category=_optional_str(metadata.get("category")),
            higher_is_better=_optional_bool(metadata.get("higher_is_better")),
            source_name=_optional_str(metadata.get("source_name")),
            source_url=_optional_str(metadata.get("source_url")),
            training_start_year=int(series_df[YEAR_COLUMN].min()),
            training_end_year=int(series_df[YEAR_COLUMN].max()),
            dataset_version=_optional_str(metadata.get("dataset_version")),
            region=_optional_str(metadata.get("region")),
            income_group=_optional_str(metadata.get("income_group")),
            notes=_optional_str(metadata.get("notes")),
            missing_years=missing_years,
        ),
        warnings=warnings,
    )


def _extract_context_metadata(
    row: pd.Series[Any], *, series_df: pd.DataFrame
) -> dict[str, Any]:
    metadata: dict[str, Any] = {}
    for column in _METADATA_COLUMNS:
        if column not in series_df.columns:
            continue
        metadata[column] = _scalar_or_none(row.get(column))
    return metadata


def _scalar_or_none(value: Any) -> Any:
    if pd.isna(value):
        return None
    if hasattr(value, "item"):
        return value.item()
    return value


def _optional_str(value: Any) -> str | None:
    if value is None:
        return None
    return str(value)


def _optional_bool(value: Any) -> bool | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"true", "1", "yes", "y"}:
            return True
        if lowered in {"false", "0", "no", "n"}:
            return False
    return bool(value)
