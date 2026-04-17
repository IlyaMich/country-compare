from __future__ import annotations

from collections.abc import Mapping, Sequence

import pandas as pd

SINGLE_METRIC_REQUIRED_COLUMNS: tuple[str, ...] = (
    "country_code",
    "country_name",
    "metric_id",
    "metric_name",
    "value",
    "normalized_value",
    "rank",
    "year",
)

SINGLE_METRIC_DEFAULT_COLUMNS: tuple[str, ...] = (
    "country_code",
    "country_name",
    "metric_id",
    "metric_name",
    "value",
    "normalized_value",
    "rank",
    "year",
    "unit",
    "normalization_method",
    "normalization_basis",
    "rank_method",
)

MULTI_METRIC_LONG_REQUIRED_COLUMNS: tuple[str, ...] = (
    "country_code",
    "country_name",
    "metric_id",
    "metric_name",
    "value",
    "normalized_value",
    "rank",
    "year",
)

MULTI_METRIC_LONG_DEFAULT_COLUMNS: tuple[str, ...] = (
    "metric_id",
    "metric_name",
    "country_code",
    "country_name",
    "value",
    "normalized_value",
    "rank",
    "year",
    "unit",
    "category",
    "normalization_method",
    "normalization_basis",
    "rank_method",
)

WEIGHTED_SCORE_REQUIRED_COLUMNS: tuple[str, ...] = (
    "country_code",
    "country_name",
    "weighted_score",
    "score_rank",
)

WEIGHTED_SCORE_DEFAULT_COLUMNS: tuple[str, ...] = (
    "country_code",
    "country_name",
    "weighted_score",
    "score_rank",
    "profile_name",
    "missing_data_policy",
    "metric_count_used",
    "metric_count_expected",
    "missing_metric_count",
    "missing_metrics",
    "weight_sum_used",
    "year_strategy",
    "score_rank_method",
)

DEFAULT_WIDE_ID_COLUMNS: tuple[str, ...] = (
    "country_code",
    "country_name",
)


def make_single_metric_table(
    df: pd.DataFrame,
    *,
    columns: Sequence[str] | None = None,
    rename_columns: Mapping[str, str] | None = None,
    sort_by: str | Sequence[str] | None = "rank",
    ascending: bool | Sequence[bool] = True,
    round_ndigits: int | Mapping[str, int] | None = None,
    top_n: int | None = None,
) -> pd.DataFrame:
    """
    Format a single-metric comparison dataframe for reporting.

    The input is expected to come from ``compare_metric(...)`` and already contain
    ranking and normalization results.
    """
    return _make_table(
        df,
        required_columns=SINGLE_METRIC_REQUIRED_COLUMNS,
        default_columns=SINGLE_METRIC_DEFAULT_COLUMNS,
        columns=columns,
        rename_columns=rename_columns,
        sort_by=sort_by,
        ascending=ascending,
        round_ndigits=round_ndigits,
        top_n=top_n,
        context="single metric table",
    )



def make_multi_metric_long_table(
    df: pd.DataFrame,
    *,
    columns: Sequence[str] | None = None,
    rename_columns: Mapping[str, str] | None = None,
    sort_by: str | Sequence[str] | None = ("metric_id", "rank", "country_name"),
    ascending: bool | Sequence[bool] = (True, True, True),
    round_ndigits: int | Mapping[str, int] | None = None,
    top_n: int | None = None,
) -> pd.DataFrame:
    """
    Format a long-form multi-metric comparison dataframe for reporting.

    The input is expected to come from ``compare_countries(...)``.
    """
    return _make_table(
        df,
        required_columns=MULTI_METRIC_LONG_REQUIRED_COLUMNS,
        default_columns=MULTI_METRIC_LONG_DEFAULT_COLUMNS,
        columns=columns,
        rename_columns=rename_columns,
        sort_by=sort_by,
        ascending=ascending,
        round_ndigits=round_ndigits,
        top_n=top_n,
        context="multi metric long table",
    )



def make_multi_metric_wide_table(
    df: pd.DataFrame,
    *,
    columns: Sequence[str] | None = None,
    rename_columns: Mapping[str, str] | None = None,
    sort_by: str | Sequence[str] | None = None,
    ascending: bool | Sequence[bool] = True,
    round_ndigits: int | Mapping[str, int] | None = None,
    top_n: int | None = None,
) -> pd.DataFrame:
    """
    Format a wide multi-metric comparison dataframe for reporting.

    The input is expected to come from ``build_multi_metric_wide_table(...)``.
    """
    _require_any_columns(df, DEFAULT_WIDE_ID_COLUMNS, context="multi metric wide table")

    default_columns = _resolve_wide_default_columns(df)
    resolved_sort_by: str | Sequence[str] | None = sort_by
    if resolved_sort_by is None:
        if "country_name" in df.columns:
            resolved_sort_by = "country_name"
        elif "country_code" in df.columns:
            resolved_sort_by = "country_code"

    return _make_table(
        df,
        required_columns=(),
        default_columns=default_columns,
        columns=columns,
        rename_columns=rename_columns,
        sort_by=resolved_sort_by,
        ascending=ascending,
        round_ndigits=round_ndigits,
        top_n=top_n,
        context="multi metric wide table",
    )



def make_weighted_score_table(
    df: pd.DataFrame,
    *,
    columns: Sequence[str] | None = None,
    rename_columns: Mapping[str, str] | None = None,
    sort_by: str | Sequence[str] | None = "score_rank",
    ascending: bool | Sequence[bool] = True,
    round_ndigits: int | Mapping[str, int] | None = None,
    top_n: int | None = None,
) -> pd.DataFrame:
    """
    Format a weighted-score dataframe for reporting.

    The input is expected to come from ``score_countries(...)``.
    """
    return _make_table(
        df,
        required_columns=WEIGHTED_SCORE_REQUIRED_COLUMNS,
        default_columns=WEIGHTED_SCORE_DEFAULT_COLUMNS,
        columns=columns,
        rename_columns=rename_columns,
        sort_by=sort_by,
        ascending=ascending,
        round_ndigits=round_ndigits,
        top_n=top_n,
        context="weighted score table",
    )



def _make_table(
    df: pd.DataFrame,
    *,
    required_columns: Sequence[str],
    default_columns: Sequence[str],
    columns: Sequence[str] | None,
    rename_columns: Mapping[str, str] | None,
    sort_by: str | Sequence[str] | None,
    ascending: bool | Sequence[bool],
    round_ndigits: int | Mapping[str, int] | None,
    top_n: int | None,
    context: str,
) -> pd.DataFrame:
    _require_columns(df, required_columns, context=context)

    result = df.copy(deep=True)

    resolved_columns = list(columns) if columns is not None else _available_columns(result, default_columns)
    missing_selected = [column for column in resolved_columns if column not in result.columns]
    if missing_selected:
        raise ValueError(
            f"{context} requested columns that are not present in the dataframe: {missing_selected}"
        )

    result = result.loc[:, resolved_columns].copy()

    if sort_by is not None:
        sort_columns = [sort_by] if isinstance(sort_by, str) else list(sort_by)
        missing_sort_columns = [column for column in sort_columns if column not in result.columns]
        if missing_sort_columns:
            raise ValueError(
                f"{context} cannot sort by missing columns: {missing_sort_columns}"
            )
        resolved_ascending = _normalize_ascending(ascending, expected_length=len(sort_columns))
        result = result.sort_values(by=sort_columns, ascending=resolved_ascending, kind="stable")

    if top_n is not None:
        if top_n < 0:
            raise ValueError(f"{context} top_n must be >= 0")
        result = result.head(top_n).copy()

    if round_ndigits is not None:
        result = _round_numeric_columns(result, round_ndigits)

    if rename_columns:
        missing_rename_columns = [column for column in rename_columns if column not in result.columns]
        if missing_rename_columns:
            raise ValueError(
                f"{context} cannot rename missing columns: {missing_rename_columns}"
            )
        result = result.rename(columns=dict(rename_columns))

    result = result.reset_index(drop=True)
    return result



def _resolve_wide_default_columns(df: pd.DataFrame) -> list[str]:
    id_columns = [column for column in DEFAULT_WIDE_ID_COLUMNS if column in df.columns]
    metric_columns = [column for column in df.columns if column not in id_columns]
    metric_columns.sort()
    return [*id_columns, *metric_columns]



def _available_columns(df: pd.DataFrame, columns: Sequence[str]) -> list[str]:
    return [column for column in columns if column in df.columns]


def _normalize_ascending(
    ascending: bool | Sequence[bool],
    *,
    expected_length: int,
) -> bool | list[bool]:
    if isinstance(ascending, bool):
        return ascending

    resolved = list(ascending)
    if len(resolved) == expected_length:
        return resolved
    if len(resolved) == 1:
        return resolved * expected_length
    if len(resolved) > expected_length:
        return resolved[:expected_length]

    raise ValueError(
        f"ascending length {len(resolved)} does not match sort column length {expected_length}"
    )



def _require_columns(df: pd.DataFrame, columns: Sequence[str], *, context: str) -> None:
    missing = [column for column in columns if column not in df.columns]
    if missing:
        raise ValueError(f"{context} requires columns that are missing: {missing}")



def _require_any_columns(df: pd.DataFrame, columns: Sequence[str], *, context: str) -> None:
    if any(column in df.columns for column in columns):
        return
    raise ValueError(
        f"{context} requires at least one of the following columns: {list(columns)}"
    )



def _round_numeric_columns(
    df: pd.DataFrame,
    round_ndigits: int | Mapping[str, int],
) -> pd.DataFrame:
    result = df.copy(deep=True)

    if isinstance(round_ndigits, Mapping):
        for column, digits in round_ndigits.items():
            if column not in result.columns:
                continue
            if pd.api.types.is_numeric_dtype(result[column]):
                result[column] = result[column].round(int(digits))
        return result

    numeric_columns = result.select_dtypes(include=["number"]).columns.tolist()
    if numeric_columns:
        result.loc[:, numeric_columns] = result.loc[:, numeric_columns].round(int(round_ndigits))
    return result


__all__ = [
    "make_single_metric_table",
    "make_multi_metric_long_table",
    "make_multi_metric_wide_table",
    "make_weighted_score_table",
    "SINGLE_METRIC_REQUIRED_COLUMNS",
    "MULTI_METRIC_LONG_REQUIRED_COLUMNS",
    "WEIGHTED_SCORE_REQUIRED_COLUMNS",
]
