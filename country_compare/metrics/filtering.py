from __future__ import annotations

from collections.abc import Iterable

import pandas as pd

from country_compare.config.models import YearStrategy
from country_compare.data.contract import (
    COUNTRY_CODE_COLUMN,
    METRIC_ID_COLUMN,
    YEAR_COLUMN,
)


def filter_countries(
    df: pd.DataFrame,
    *,
    include: Iterable[str] | None = None,
    exclude: Iterable[str] | None = None,
) -> pd.DataFrame:
    """
    Return a filtered copy of the canonical dataset using country_code values.

    Parameters
    ----------
    df:
        Canonical long-format metric dataframe.
    include:
        Optional iterable of country codes to keep.
    exclude:
        Optional iterable of country codes to remove.

    Returns
    -------
    pd.DataFrame
        A new dataframe preserving the input schema, column order, and dtypes.

    Notes
    -----
    - Filtering is applied on ``country_code`` only.
    - Input is never mutated.
    - Empty include/exclude collections are treated as no-op filters.
    """
    include_codes = _normalize_string_filters(include, uppercase=True)
    exclude_codes = _normalize_string_filters(exclude, uppercase=True)

    result = df.copy()

    if COUNTRY_CODE_COLUMN not in result.columns:
        raise ValueError(
            f"dataframe must contain '{COUNTRY_CODE_COLUMN}' to filter countries"
        )

    country_series = result[COUNTRY_CODE_COLUMN].astype("string").str.upper()

    if include_codes is not None:
        result = result.loc[country_series.isin(include_codes)].copy()

    if exclude_codes is not None:
        result = result.loc[
            ~result[COUNTRY_CODE_COLUMN]
            .astype("string")
            .str.upper()
            .isin(exclude_codes)
        ].copy()

    return result


def filter_metrics(
    df: pd.DataFrame,
    *,
    include: Iterable[str] | None = None,
    exclude: Iterable[str] | None = None,
) -> pd.DataFrame:
    """
    Return a filtered copy of the canonical dataset using metric_id values.

    Parameters
    ----------
    df:
        Canonical long-format metric dataframe.
    include:
        Optional iterable of metric IDs to keep.
    exclude:
        Optional iterable of metric IDs to remove.

    Returns
    -------
    pd.DataFrame
        A new dataframe preserving the input schema, column order, and dtypes.

    Notes
    -----
    - Filtering is applied on ``metric_id`` only.
    - Input is never mutated.
    - Metric semantics are not interpreted here; config alignment remains external.
    """
    include_metrics = _normalize_string_filters(include, uppercase=False)
    exclude_metrics = _normalize_string_filters(exclude, uppercase=False)

    result = df.copy()

    if METRIC_ID_COLUMN not in result.columns:
        raise ValueError(
            f"dataframe must contain '{METRIC_ID_COLUMN}' to filter metrics"
        )

    metric_series = result[METRIC_ID_COLUMN].astype("string")

    if include_metrics is not None:
        result = result.loc[metric_series.isin(include_metrics)].copy()

    if exclude_metrics is not None:
        result = result.loc[
            ~result[METRIC_ID_COLUMN].astype("string").isin(exclude_metrics)
        ].copy()

    return result


def apply_year_strategy(
    df: pd.DataFrame,
    strategy: YearStrategy | str,
    *,
    target_year: int | None = None,
) -> pd.DataFrame:
    """
    Apply one of the configured year-selection strategies.

    Supported strategies come from :class:`country_compare.config.models.YearStrategy`.

    Parameters
    ----------
    df:
        Canonical long-format metric dataframe.
    strategy:
        A YearStrategy enum member or its string value.
    target_year:
        Required when ``strategy`` is ``TARGET_YEAR``.

    Returns
    -------
    pd.DataFrame
        A filtered dataframe matching the requested year selection behavior.
    """
    resolved_strategy = YearStrategy(strategy)

    if resolved_strategy == YearStrategy.LATEST_PER_METRIC:
        return select_latest_per_metric(df)
    if resolved_strategy == YearStrategy.TARGET_YEAR:
        return select_target_year(df, target_year=target_year)
    if resolved_strategy == YearStrategy.COMMON_YEAR:
        return select_common_year(df)

    # Defensive branch for forward compatibility with enum expansion.
    raise ValueError(f"unsupported year strategy: {resolved_strategy!r}")


def select_latest_per_metric(df: pd.DataFrame) -> pd.DataFrame:
    """
    Select the latest available year for each (country_code, metric_id) pair.

    Example:
        If GDP exists for 2022 and 2023 for a country, but rule_of_law exists only
        for 2022, the output keeps GDP at 2023 and rule_of_law at 2022.
    """
    _require_columns(df, [COUNTRY_CODE_COLUMN, METRIC_ID_COLUMN, YEAR_COLUMN])

    if df.empty:
        return df.copy()

    year_numeric = pd.to_numeric(df[YEAR_COLUMN], errors="coerce")
    latest_year_per_pair = year_numeric.groupby(
        [df[COUNTRY_CODE_COLUMN], df[METRIC_ID_COLUMN]]
    ).transform("max")

    result = df.loc[year_numeric.eq(latest_year_per_pair)].copy()
    return result


def select_target_year(
    df: pd.DataFrame,
    *,
    target_year: int | None,
) -> pd.DataFrame:
    """
    Select rows for a single target year.

    Parameters
    ----------
    target_year:
        Required integer year to keep.
    """
    _require_columns(df, [YEAR_COLUMN])

    if target_year is None:
        raise ValueError(
            "target_year must be provided when using YearStrategy.TARGET_YEAR"
        )

    year_numeric = pd.to_numeric(df[YEAR_COLUMN], errors="coerce")
    return df.loc[year_numeric.eq(int(target_year))].copy()


def select_common_year(df: pd.DataFrame) -> pd.DataFrame:
    """
    Select the latest year that provides full country/metric coverage.

    Full coverage means the chosen year contains every combination from the
    cartesian product of the currently present country_code values and metric_id
    values in the input slice.

    Raises
    ------
    ValueError
        If no such common year exists.
    """
    _require_columns(df, [COUNTRY_CODE_COLUMN, METRIC_ID_COLUMN, YEAR_COLUMN])

    if df.empty:
        return df.copy()

    country_count = df[COUNTRY_CODE_COLUMN].dropna().nunique()
    metric_count = df[METRIC_ID_COLUMN].dropna().nunique()

    if country_count == 0 or metric_count == 0:
        return df.iloc[0:0].copy()

    expected_pair_count = country_count * metric_count

    pair_counts_by_year = (
        df[[COUNTRY_CODE_COLUMN, METRIC_ID_COLUMN, YEAR_COLUMN]]
        .dropna(subset=[COUNTRY_CODE_COLUMN, METRIC_ID_COLUMN, YEAR_COLUMN])
        .drop_duplicates(subset=[COUNTRY_CODE_COLUMN, METRIC_ID_COLUMN, YEAR_COLUMN])
        .groupby(YEAR_COLUMN)
        .size()
    )

    valid_years = pair_counts_by_year.loc[pair_counts_by_year.eq(expected_pair_count)]

    if valid_years.empty:
        countries = sorted(
            df[COUNTRY_CODE_COLUMN].dropna().astype(str).unique().tolist()
        )
        metrics = sorted(df[METRIC_ID_COLUMN].dropna().astype(str).unique().tolist())
        raise ValueError(
            "no common year provides full coverage for the current dataset slice; "
            f"countries={countries}, metrics={metrics}"
        )

    selected_year = int(valid_years.index.max())
    return select_target_year(df, target_year=selected_year)


def filter_dataset(
    df: pd.DataFrame,
    *,
    countries_include: Iterable[str] | None = None,
    countries_exclude: Iterable[str] | None = None,
    metrics_include: Iterable[str] | None = None,
    metrics_exclude: Iterable[str] | None = None,
    year_strategy: YearStrategy | str | None = None,
    target_year: int | None = None,
) -> pd.DataFrame:
    """
    Apply the Phase 5 filtering pipeline to a canonical dataframe.

    Pipeline order:
        Load dataframe -> filter countries -> filter metrics -> apply year strategy

    Parameters
    ----------
    df:
        Canonical long-format metric dataframe.
    countries_include, countries_exclude:
        Country-code filters applied on ``country_code``.
    metrics_include, metrics_exclude:
        Metric-ID filters applied on ``metric_id``.
    year_strategy:
        Optional year strategy. When omitted, year filtering is skipped.
    target_year:
        Used only for ``YearStrategy.TARGET_YEAR``.
    """
    filtered = filter_countries(
        df,
        include=countries_include,
        exclude=countries_exclude,
    )
    filtered = filter_metrics(
        filtered,
        include=metrics_include,
        exclude=metrics_exclude,
    )

    if year_strategy is None:
        return filtered.copy()

    return apply_year_strategy(
        filtered,
        strategy=year_strategy,
        target_year=target_year,
    )


def _normalize_string_filters(
    values: Iterable[str] | None,
    *,
    uppercase: bool,
) -> set[str] | None:
    if values is None:
        return None

    normalized: set[str] = set()
    for value in values:
        if value is None:
            continue
        text = str(value).strip()
        if not text:
            continue
        normalized.add(text.upper() if uppercase else text)

    return normalized


def _require_columns(df: pd.DataFrame, columns: list[str]) -> None:
    missing = [column for column in columns if column not in df.columns]
    if missing:
        raise ValueError(
            f"dataframe is missing required columns for filtering: {missing}"
        )
