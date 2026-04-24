from __future__ import annotations

from collections.abc import Iterable

import pandas as pd

from country_compare.data.contract import REQUIRED_COLUMNS
from country_compare.prediction.errors import PredictionErrorCode, PredictionException
from country_compare.prediction.models import (
    ForecastOptions,
    PredictionMethod,
    SingleMetricPredictionRequest,
)

COUNTRY_CODE_COLUMN = "country_code"
METRIC_ID_COLUMN = "metric_id"
YEAR_COLUMN = "year"
VALUE_COLUMN = "value"
DEFAULT_METHOD = PredictionMethod.LINEAR_TREND
DEFAULT_FALLBACK_METHOD = PredictionMethod.LAST_OBSERVED


def validate_prediction_request(
    request: SingleMetricPredictionRequest,
    *,
    options: ForecastOptions | None = None,
) -> None:
    options = options or ForecastOptions(scenario_id=request.scenario_id)

    if request.horizon_years <= 0:
        raise PredictionException(
            PredictionErrorCode.INVALID_HORIZON,
            "horizon_years must be greater than zero",
            country_code=request.country_code,
            metric_id=request.metric_id,
            details={"horizon_years": request.horizon_years},
        )

    if request.horizon_years > options.max_horizon_years:
        raise PredictionException(
            PredictionErrorCode.INVALID_HORIZON,
            f"horizon_years must be <= {options.max_horizon_years}",
            country_code=request.country_code,
            metric_id=request.metric_id,
            details={
                "horizon_years": request.horizon_years,
                "max_horizon_years": options.max_horizon_years,
            },
        )

    _resolve_method_value(request.method, field_name="method", allow_none=True)
    _resolve_method_value(
        request.fallback_method, field_name="fallback_method", allow_none=True
    )


def validate_canonical_prediction_input(dataframe: pd.DataFrame) -> None:
    missing = [column for column in REQUIRED_COLUMNS if column not in dataframe.columns]
    if missing:
        raise PredictionException(
            PredictionErrorCode.UNSUPPORTED_SERIES_SHAPE,
            f"canonical dataframe is missing required columns: {missing}",
            details={"missing_columns": missing},
        )


def validate_country_metric_presence(
    dataframe: pd.DataFrame,
    *,
    country_code: str,
    metric_id: str,
) -> None:
    validate_canonical_prediction_input(dataframe)

    country_values = _string_values(dataframe[COUNTRY_CODE_COLUMN], uppercase=True)
    if country_code.upper() not in country_values:
        raise PredictionException(
            PredictionErrorCode.MISSING_COUNTRY,
            f"country_code '{country_code}' was not found in the dataframe",
            country_code=country_code,
            metric_id=metric_id,
        )

    metric_values = _string_values(dataframe[METRIC_ID_COLUMN], uppercase=False)
    if metric_id not in metric_values:
        raise PredictionException(
            PredictionErrorCode.MISSING_METRIC,
            f"metric_id '{metric_id}' was not found in the dataframe",
            country_code=country_code,
            metric_id=metric_id,
        )


def validate_series_uniqueness(
    series_df: pd.DataFrame, *, country_code: str, metric_id: str
) -> None:
    if YEAR_COLUMN not in series_df.columns:
        raise PredictionException(
            PredictionErrorCode.UNSUPPORTED_SERIES_SHAPE,
            "prepared series is missing year column",
            country_code=country_code,
            metric_id=metric_id,
        )

    duplicate_mask = series_df.duplicated(subset=[YEAR_COLUMN], keep=False)
    if duplicate_mask.any():
        duplicate_years = (
            pd.to_numeric(series_df.loc[duplicate_mask, YEAR_COLUMN], errors="coerce")
            .dropna()
            .astype(int)
            .tolist()
        )
        raise PredictionException(
            PredictionErrorCode.DUPLICATE_SERIES_YEAR,
            "duplicate rows detected for country_code + metric_id + year",
            country_code=country_code,
            metric_id=metric_id,
            details={"duplicate_years": sorted(set(duplicate_years))},
        )


def validate_non_empty_series(
    series_df: pd.DataFrame, *, country_code: str, metric_id: str
) -> None:
    if series_df.empty:
        raise PredictionException(
            PredictionErrorCode.EMPTY_SERIES,
            "no rows remain for the requested country/metric after history filtering",
            country_code=country_code,
            metric_id=metric_id,
        )


def validate_numeric_series_values(
    series_df: pd.DataFrame, *, country_code: str, metric_id: str
) -> pd.Series:
    numeric_values = pd.to_numeric(series_df[VALUE_COLUMN], errors="coerce")
    invalid_mask = numeric_values.isna() | numeric_values.isin(
        [float("inf"), float("-inf")]
    )
    if invalid_mask.any():
        invalid_years = (
            pd.to_numeric(series_df.loc[invalid_mask, YEAR_COLUMN], errors="coerce")
            .dropna()
            .astype(int)
            .tolist()
        )
        raise PredictionException(
            PredictionErrorCode.NON_NUMERIC_VALUE,
            "series value column contains non-numeric or non-finite values",
            country_code=country_code,
            metric_id=metric_id,
            details={"invalid_years": invalid_years},
        )
    return numeric_values.astype("float64")


def identify_missing_internal_years(years: Iterable[int]) -> list[int]:
    resolved_years = sorted({int(year) for year in years})
    if len(resolved_years) < 2:
        return []
    return [
        year
        for year in range(resolved_years[0], resolved_years[-1] + 1)
        if year not in resolved_years
    ]


def resolve_requested_method(
    request: SingleMetricPredictionRequest,
) -> PredictionMethod:
    return (
        _resolve_method_value(request.method, field_name="method", allow_none=True)
        or DEFAULT_METHOD
    )


def resolve_fallback_method(
    request: SingleMetricPredictionRequest,
) -> PredictionMethod | None:
    return _resolve_method_value(
        request.fallback_method,
        field_name="fallback_method",
        allow_none=True,
    )


def _resolve_method_value(
    method: PredictionMethod | str | None,
    *,
    field_name: str,
    allow_none: bool,
) -> PredictionMethod | None:
    if method is None:
        if allow_none:
            return None
        raise PredictionException(
            PredictionErrorCode.UNSUPPORTED_METHOD,
            f"{field_name} must not be null",
        )
    try:
        return (
            method
            if isinstance(method, PredictionMethod)
            else PredictionMethod(str(method))
        )
    except ValueError as exc:
        raise PredictionException(
            PredictionErrorCode.UNSUPPORTED_METHOD,
            f"unsupported prediction {field_name}: {method!r}",
            details={field_name: str(method)},
        ) from exc


def _string_values(series: pd.Series, *, uppercase: bool) -> set[str]:
    values = set()
    for value in series.dropna().astype("string").tolist():
        text = str(value).strip()
        if text:
            values.add(text.upper() if uppercase else text)
    return values
