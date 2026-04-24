from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence

import pandas as pd

from country_compare.comparison.single_metric import (
    RANK_COLUMN,
    RANK_METHOD_COLUMN,
    ComparisonError,
    rank_metric,
)
from country_compare.config.models import (
    MetricsConfig,
    NormalizationMethod,
    ScoringConfig,
    YearStrategy,
)
from country_compare.metrics.filtering import filter_dataset
from country_compare.metrics.normalization import (
    NORMALIZATION_BASIS_COLUMN,
    NORMALIZATION_METHOD_COLUMN,
    NORMALIZED_VALUE_COLUMN,
    NormalizationError,
    normalize_dataframe,
)

COUNTRY_CODE_COLUMN = "country_code"
COUNTRY_NAME_COLUMN = "country_name"
METRIC_ID_COLUMN = "metric_id"
YEAR_COLUMN = "year"
DEFAULT_WIDE_VALUE_COLUMNS: tuple[str, ...] = (
    "value",
    NORMALIZED_VALUE_COLUMN,
    RANK_COLUMN,
    YEAR_COLUMN,
)
DEFAULT_WIDE_COUNTRY_COLUMNS: tuple[str, ...] = (
    COUNTRY_CODE_COLUMN,
    COUNTRY_NAME_COLUMN,
    "region",
    "income_group",
)


def prepare_multi_metric_slice(
    dataframe: pd.DataFrame,
    *,
    metric_ids: Iterable[str] | None = None,
    countries_include: Iterable[str] | None = None,
    countries_exclude: Iterable[str] | None = None,
    year_strategy: YearStrategy | str = YearStrategy.LATEST_PER_METRIC,
    target_year: int | None = None,
    scoring_config: ScoringConfig | None = None,
    profile_name: str | None = None,
) -> pd.DataFrame:
    """
    Build a filtered multi-metric comparison slice from the canonical dataframe.

    The returned slice remains in long format and contains at most one row per
    ``country_code`` + ``metric_id`` pair after year selection.
    """
    resolved_metric_ids = _resolve_metric_ids(
        metric_ids=metric_ids,
        scoring_config=scoring_config,
        profile_name=profile_name,
    )

    available_metric_ids = set(
        dataframe[METRIC_ID_COLUMN].dropna().astype("string").unique().tolist()
    )
    missing_metric_ids = [
        metric_id
        for metric_id in resolved_metric_ids
        if metric_id not in available_metric_ids
    ]
    if missing_metric_ids:
        raise ComparisonError(
            "requested metric_id values were not found in the dataframe: "
            f"{sorted(missing_metric_ids)}"
        )

    try:
        prepared = filter_dataset(
            dataframe.copy(deep=True),
            countries_include=countries_include,
            countries_exclude=countries_exclude,
            metrics_include=resolved_metric_ids,
            year_strategy=year_strategy,
            target_year=target_year,
        )
    except ValueError as exc:
        raise ComparisonError(str(exc)) from exc

    if prepared.empty:
        raise ComparisonError(
            "no rows remain after applying metric/country/year filters"
        )

    _validate_multi_metric_slice(prepared)
    return prepared.copy(deep=True)


def rank_multi_metric(dataframe: pd.DataFrame) -> pd.DataFrame:
    """
    Apply Phase 7 per-metric ranking semantics across a multi-metric long slice.

    Each metric is ranked independently, so rank 1 always means the best country
    within that metric after normalization.
    """
    _require_columns(dataframe, [METRIC_ID_COLUMN, NORMALIZED_VALUE_COLUMN])

    if dataframe.empty:
        result = dataframe.copy(deep=True)
        result[RANK_COLUMN] = pd.Series(index=result.index, dtype="Int64")
        result[RANK_METHOD_COLUMN] = pd.Series(index=result.index, dtype="string")
        return result

    ranked_groups: list[pd.DataFrame] = []
    for _, metric_df in dataframe.groupby(METRIC_ID_COLUMN, sort=True, dropna=False):
        ranked_groups.append(rank_metric(metric_df))

    result = pd.concat(ranked_groups, ignore_index=True)
    result = result.sort_values(
        by=[METRIC_ID_COLUMN, RANK_COLUMN, COUNTRY_NAME_COLUMN, COUNTRY_CODE_COLUMN],
        ascending=[True, True, True, True],
        kind="mergesort",
        na_position="last",
    ).reset_index(drop=True)
    return result


def compare_countries(
    dataframe: pd.DataFrame,
    *,
    metric_ids: Iterable[str] | None = None,
    countries_include: Iterable[str] | None = None,
    countries_exclude: Iterable[str] | None = None,
    year_strategy: YearStrategy | str = YearStrategy.LATEST_PER_METRIC,
    target_year: int | None = None,
    normalization_method: NormalizationMethod | str | None = None,
    normalization_method_overrides: (
        Mapping[str, NormalizationMethod | str] | None
    ) = None,
    metrics_config: MetricsConfig | None = None,
    scoring_config: ScoringConfig | None = None,
    profile_name: str | None = None,
) -> pd.DataFrame:
    """
    Compare countries across multiple metrics in long format.

    Workflow:
    1. select requested metrics
    2. apply country filters
    3. apply year strategy
    4. normalize each metric across the current filtered slice
    5. rank countries independently within each metric
    """
    prepared = prepare_multi_metric_slice(
        dataframe,
        metric_ids=metric_ids,
        countries_include=countries_include,
        countries_exclude=countries_exclude,
        year_strategy=year_strategy,
        target_year=target_year,
        scoring_config=scoring_config,
        profile_name=profile_name,
    )

    try:
        normalized = normalize_dataframe(
            prepared,
            metrics_config=metrics_config,
            scoring_config=scoring_config,
            profile_name=profile_name,
            method=normalization_method,
            method_overrides=normalization_method_overrides,
        )
    except NormalizationError as exc:
        raise ComparisonError(str(exc)) from exc
    except ValueError as exc:
        raise ComparisonError(str(exc)) from exc

    ranked = rank_multi_metric(normalized)
    return ranked.copy(deep=True)


def build_multi_metric_wide_table(
    dataframe: pd.DataFrame,
    *,
    value_columns: Sequence[str] = DEFAULT_WIDE_VALUE_COLUMNS,
    country_columns: Sequence[str] | None = None,
    metric_order: Sequence[str] | None = None,
) -> pd.DataFrame:
    """
    Pivot a long multi-metric comparison dataframe into a wide country table.

    Output columns are flattened using ``<metric_id>__<value_column>``.
    Example: ``gdp_per_capita__normalized_value``.
    """
    _require_columns(dataframe, [COUNTRY_CODE_COLUMN, METRIC_ID_COLUMN, *value_columns])

    selected_country_columns = _resolve_country_columns(dataframe, country_columns)

    duplicate_pairs = dataframe.duplicated(
        subset=[COUNTRY_CODE_COLUMN, METRIC_ID_COLUMN],
        keep=False,
    )
    if duplicate_pairs.any():
        duplicate_rows = dataframe.loc[
            duplicate_pairs,
            [COUNTRY_CODE_COLUMN, METRIC_ID_COLUMN, YEAR_COLUMN],
        ]
        raise ComparisonError(
            "wide table requires at most one row per country_code + metric_id. "
            f"Duplicates={duplicate_rows.to_dict(orient='records')}"
        )

    if metric_order is None:
        metric_order = sorted(
            dataframe[METRIC_ID_COLUMN].dropna().astype("string").unique().tolist()
        )

    base = (
        dataframe[selected_country_columns]
        .drop_duplicates(subset=[COUNTRY_CODE_COLUMN])
        .set_index(COUNTRY_CODE_COLUMN)
    )

    pivot = dataframe.pivot(
        index=COUNTRY_CODE_COLUMN,
        columns=METRIC_ID_COLUMN,
        values=list(value_columns),
    )

    wide_parts: list[pd.Series] = []
    for metric_id in metric_order:
        for value_column in value_columns:
            key = (value_column, metric_id)
            if key not in pivot.columns:
                continue
            series = pivot[key].rename(f"{metric_id}__{value_column}")
            wide_parts.append(series)

    if wide_parts:
        wide_values = pd.concat(wide_parts, axis=1)
        result = base.join(wide_values, how="left")
    else:
        result = base.copy()

    result = result.reset_index()
    sort_columns = [
        column
        for column in [COUNTRY_NAME_COLUMN, COUNTRY_CODE_COLUMN]
        if column in result.columns
    ]
    if sort_columns:
        result = result.sort_values(
            by=sort_columns,
            ascending=[True] * len(sort_columns),
            kind="mergesort",
            na_position="last",
        ).reset_index(drop=True)
    return result


def _resolve_metric_ids(
    *,
    metric_ids: Iterable[str] | None,
    scoring_config: ScoringConfig | None,
    profile_name: str | None,
) -> list[str]:
    resolved: list[str] = []

    if metric_ids is not None:
        resolved = _normalize_string_list(metric_ids)
    elif profile_name is not None:
        if scoring_config is None:
            raise ComparisonError(
                "scoring_config must be provided when profile_name is used to resolve metrics"
            )
        if profile_name not in scoring_config.profiles:
            raise ComparisonError(f"unknown scoring profile: {profile_name}")
        resolved = _normalize_string_list(scoring_config.profiles[profile_name].metrics)

    if not resolved:
        raise ComparisonError(
            "at least one metric_id must be provided for multi-metric comparison"
        )

    return resolved


def _resolve_country_columns(
    dataframe: pd.DataFrame,
    country_columns: Sequence[str] | None,
) -> list[str]:
    if country_columns is None:
        return [
            column
            for column in DEFAULT_WIDE_COUNTRY_COLUMNS
            if column in dataframe.columns
        ]

    _require_columns(dataframe, country_columns)
    return list(country_columns)


def _normalize_string_list(values: Iterable[str]) -> list[str]:
    normalized: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = str(value).strip()
        if not text or text in seen:
            continue
        normalized.append(text)
        seen.add(text)
    return normalized


def _validate_multi_metric_slice(dataframe: pd.DataFrame) -> None:
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
            "duplicate rows detected for the multi-metric comparison slice after "
            "year selection; expected at most one row per country/metric/year. "
            f"Duplicates={duplicate_rows.to_dict(orient='records')}"
        )

    duplicate_country_metric = dataframe.duplicated(
        subset=[COUNTRY_CODE_COLUMN, METRIC_ID_COLUMN],
        keep=False,
    )
    if duplicate_country_metric.any():
        duplicate_rows = dataframe.loc[
            duplicate_country_metric,
            [COUNTRY_CODE_COLUMN, METRIC_ID_COLUMN, YEAR_COLUMN],
        ]
        raise ComparisonError(
            "multi-metric comparison requires at most one row per country + metric "
            "after year selection. Duplicate pairs remained in the slice: "
            f"{duplicate_rows.to_dict(orient='records')}"
        )


def _require_columns(dataframe: pd.DataFrame, columns: Sequence[str]) -> None:
    missing = [column for column in columns if column not in dataframe.columns]
    if missing:
        raise ComparisonError(
            f"dataframe is missing required columns for multi-metric comparison: {missing}"
        )


__all__ = [
    "NORMALIZED_VALUE_COLUMN",
    "NORMALIZATION_METHOD_COLUMN",
    "NORMALIZATION_BASIS_COLUMN",
    "RANK_COLUMN",
    "RANK_METHOD_COLUMN",
    "ComparisonError",
    "DEFAULT_WIDE_VALUE_COLUMNS",
    "prepare_multi_metric_slice",
    "rank_multi_metric",
    "compare_countries",
    "build_multi_metric_wide_table",
]
