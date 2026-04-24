from __future__ import annotations

from collections.abc import Iterable, Sequence

import pandas as pd

from country_compare.config.models import (
    MetricsConfig,
    NormalizationMethod,
    ScoringConfig,
    YearStrategy,
)
from country_compare.metrics.filtering import filter_dataset, filter_metrics
from country_compare.metrics.normalization import (
    NORMALIZATION_BASIS_COLUMN,
    NORMALIZATION_METHOD_COLUMN,
    NORMALIZED_VALUE_COLUMN,
    NormalizationError,
    normalize_metric,
    resolve_normalization_methods,
)

COUNTRY_CODE_COLUMN = "country_code"
COUNTRY_NAME_COLUMN = "country_name"
METRIC_ID_COLUMN = "metric_id"
YEAR_COLUMN = "year"
RANK_COLUMN = "rank"
RANK_METHOD_COLUMN = "rank_method"
DEFAULT_RANK_METHOD = "competition_min"
DEFAULT_TIEBREAK_COLUMNS: tuple[str, ...] = (
    COUNTRY_NAME_COLUMN,
    COUNTRY_CODE_COLUMN,
)


class ComparisonError(ValueError):
    """Raised when a single-metric comparison cannot be completed."""


def prepare_single_metric_slice(
    dataframe: pd.DataFrame,
    *,
    metric_id: str,
    countries_include: Iterable[str] | None = None,
    countries_exclude: Iterable[str] | None = None,
    year_strategy: YearStrategy | str = YearStrategy.LATEST_PER_METRIC,
    target_year: int | None = None,
) -> pd.DataFrame:
    """
    Build a single-metric comparison slice from the canonical long-format dataframe.

    Workflow:
    1. Validate that the requested metric exists in the provided dataframe.
    2. Restrict the slice to the requested metric.
    3. Apply optional country filters.
    4. Apply the requested year strategy.
    5. Validate that the resulting slice contains at most one row per country.
    """
    working = dataframe.copy(deep=True)
    metric_scope = filter_metrics(working, include=[metric_id])

    if metric_scope.empty:
        raise ComparisonError(f"metric_id '{metric_id}' was not found in the dataframe")

    prepared = filter_dataset(
        metric_scope,
        countries_include=countries_include,
        countries_exclude=countries_exclude,
        year_strategy=year_strategy,
        target_year=target_year,
    )

    if prepared.empty:
        raise ComparisonError(
            f"no rows remain for metric_id '{metric_id}' after applying filters"
        )

    _validate_single_metric_slice(prepared, metric_id=metric_id)
    return prepared.copy(deep=True)


def resolve_single_metric_normalization_method(
    dataframe: pd.DataFrame,
    *,
    metrics_config: MetricsConfig | None = None,
    scoring_config: ScoringConfig | None = None,
    profile_name: str | None = None,
    normalization_method: NormalizationMethod | str | None = None,
) -> NormalizationMethod:
    """Resolve the effective normalization method for a prepared single-metric slice."""
    try:
        methods = resolve_normalization_methods(
            dataframe,
            metrics_config=metrics_config,
            scoring_config=scoring_config,
            profile_name=profile_name,
            method=normalization_method,
        )
    except NormalizationError as exc:
        raise ComparisonError(str(exc)) from exc

    metric_ids = dataframe[METRIC_ID_COLUMN].dropna().astype("string").unique().tolist()
    if len(metric_ids) != 1:
        raise ComparisonError(
            "single metric normalization resolution expects exactly one metric_id "
            f"in the slice; found {sorted(str(value) for value in metric_ids)}"
        )

    return methods[str(metric_ids[0])]


def rank_metric(
    dataframe: pd.DataFrame,
    *,
    normalized_value_column: str = NORMALIZED_VALUE_COLUMN,
    rank_column: str = RANK_COLUMN,
    rank_method_column: str = RANK_METHOD_COLUMN,
    tie_break_columns: Sequence[str] = DEFAULT_TIEBREAK_COLUMNS,
) -> pd.DataFrame:
    """
    Rank a normalized single-metric dataframe so rank 1 always means best.

    Ranking is based only on ``normalized_value`` and always uses descending order.
    Tied countries receive the same rank using competition ranking semantics
    (``1, 1, 3``). Output ordering is made deterministic by sorting ties with the
    provided tiebreak columns.
    """
    if normalized_value_column not in dataframe.columns:
        raise ComparisonError(
            f"dataframe must contain '{normalized_value_column}' before ranking"
        )

    missing_tiebreaks = [
        column for column in tie_break_columns if column not in dataframe.columns
    ]
    if missing_tiebreaks:
        raise ComparisonError(
            "dataframe is missing required tie-break columns for deterministic "
            f"ordering: {missing_tiebreaks}"
        )

    result = dataframe.copy(deep=True)

    if result.empty:
        result[rank_column] = pd.Series(index=result.index, dtype="Int64")
        result[rank_method_column] = pd.Series(index=result.index, dtype="string")
        return result

    result[rank_column] = (
        result[normalized_value_column]
        .rank(method="min", ascending=False)
        .astype("Int64")
    )
    result[rank_method_column] = pd.Series(
        DEFAULT_RANK_METHOD,
        index=result.index,
        dtype="string",
    )

    sort_columns = [rank_column, *tie_break_columns]
    result = result.sort_values(
        by=sort_columns,
        ascending=[True] * len(sort_columns),
        kind="mergesort",
        na_position="last",
    ).reset_index(drop=True)
    return result


def compare_metric(
    dataframe: pd.DataFrame,
    *,
    metric_id: str,
    countries_include: Iterable[str] | None = None,
    countries_exclude: Iterable[str] | None = None,
    year_strategy: YearStrategy | str = YearStrategy.LATEST_PER_METRIC,
    target_year: int | None = None,
    normalization_method: NormalizationMethod | str | None = None,
    metrics_config: MetricsConfig | None = None,
    scoring_config: ScoringConfig | None = None,
    profile_name: str | None = None,
) -> pd.DataFrame:
    """
    Compare countries on a single metric using filtering, normalization, and ranking.

    Output preserves canonical columns and appends:
    ``normalized_value``, ``normalization_method``, ``normalization_basis``,
    ``rank``, and ``rank_method``.
    """
    prepared = prepare_single_metric_slice(
        dataframe,
        metric_id=metric_id,
        countries_include=countries_include,
        countries_exclude=countries_exclude,
        year_strategy=year_strategy,
        target_year=target_year,
    )

    resolved_method = resolve_single_metric_normalization_method(
        prepared,
        metrics_config=metrics_config,
        scoring_config=scoring_config,
        profile_name=profile_name,
        normalization_method=normalization_method,
    )

    try:
        normalized = normalize_metric(prepared, method=resolved_method)
    except NormalizationError as exc:
        raise ComparisonError(str(exc)) from exc
    except ValueError as exc:
        raise ComparisonError(str(exc)) from exc

    ranked = rank_metric(normalized)
    return ranked.copy(deep=True)


def _validate_single_metric_slice(dataframe: pd.DataFrame, *, metric_id: str) -> None:
    metric_ids = dataframe[METRIC_ID_COLUMN].dropna().astype("string").unique().tolist()
    if len(metric_ids) != 1 or str(metric_ids[0]) != metric_id:
        raise ComparisonError(
            "prepared single-metric slice must contain exactly one metric_id; "
            f"found {sorted(str(value) for value in metric_ids)}"
        )

    _require_columns(dataframe, [COUNTRY_CODE_COLUMN, METRIC_ID_COLUMN, YEAR_COLUMN])

    duplicate_primary_keys = dataframe.duplicated(
        subset=[COUNTRY_CODE_COLUMN, METRIC_ID_COLUMN, YEAR_COLUMN],
        keep=False,
    )
    if duplicate_primary_keys.any():
        duplicate_rows = dataframe.loc[
            duplicate_primary_keys,
            [COUNTRY_CODE_COLUMN, METRIC_ID_COLUMN, YEAR_COLUMN],
        ]
        raise ComparisonError(
            "duplicate rows detected for the single-metric comparison slice after "
            "year selection; expected at most one row per country/metric/year. "
            f"Duplicates={duplicate_rows.to_dict(orient='records')}"
        )

    duplicate_countries = dataframe.duplicated(subset=[COUNTRY_CODE_COLUMN], keep=False)
    if duplicate_countries.any():
        duplicate_rows = dataframe.loc[
            duplicate_countries,
            [COUNTRY_CODE_COLUMN, YEAR_COLUMN],
        ]
        raise ComparisonError(
            "single-metric comparison requires at most one row per country after "
            "year selection. Duplicate countries remained in the slice: "
            f"{duplicate_rows.to_dict(orient='records')}"
        )


def _require_columns(dataframe: pd.DataFrame, columns: Sequence[str]) -> None:
    missing = [column for column in columns if column not in dataframe.columns]
    if missing:
        raise ComparisonError(
            f"dataframe is missing required columns for single-metric comparison: {missing}"
        )


__all__ = [
    "NORMALIZED_VALUE_COLUMN",
    "NORMALIZATION_METHOD_COLUMN",
    "NORMALIZATION_BASIS_COLUMN",
    "RANK_COLUMN",
    "RANK_METHOD_COLUMN",
    "ComparisonError",
    "prepare_single_metric_slice",
    "resolve_single_metric_normalization_method",
    "rank_metric",
    "compare_metric",
]
