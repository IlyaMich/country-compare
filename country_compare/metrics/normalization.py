from __future__ import annotations

from collections.abc import Mapping

import numpy as np
import pandas as pd

from country_compare.config.models import (
    MetricsConfig,
    NormalizationMethod,
    ScoringConfig,
)
from country_compare.data.contract import (
    HIGHER_IS_BETTER_COLUMN,
    METRIC_ID_COLUMN,
    VALUE_COLUMN,
)
from country_compare.data.validation import validate_required_columns

NORMALIZED_VALUE_COLUMN = "normalized_value"
NORMALIZATION_METHOD_COLUMN = "normalization_method"
NORMALIZATION_BASIS_COLUMN = "normalization_basis"


class NormalizationError(ValueError):
    """Raised when normalization cannot be completed for the provided data."""


def resolve_normalization_methods(
    df: pd.DataFrame,
    *,
    metrics_config: MetricsConfig | None = None,
    scoring_config: ScoringConfig | None = None,
    profile_name: str | None = None,
    method: NormalizationMethod | str | None = None,
    method_overrides: Mapping[str, NormalizationMethod | str] | None = None,
) -> dict[str, NormalizationMethod]:
    """
    Resolve the normalization method for each metric_id in the dataframe.

    Precedence, highest to lowest:
    1. ``method_overrides`` per metric_id
    2. explicit ``method`` applied to all metrics
    3. scoring profile normalization overrides
    4. per-metric defaults from ``metrics_config``
    """
    _require_columns(df, [METRIC_ID_COLUMN])

    metric_ids = [
        str(metric_id)
        for metric_id in df[METRIC_ID_COLUMN]
        .dropna()
        .astype("string")
        .unique()
        .tolist()
    ]

    resolved_global_method = NormalizationMethod(method) if method is not None else None
    resolved_overrides = {
        str(metric_id): NormalizationMethod(value)
        for metric_id, value in (method_overrides or {}).items()
    }

    profile_overrides: dict[str, NormalizationMethod] = {}
    if profile_name is not None:
        if scoring_config is None:
            raise NormalizationError(
                "scoring_config must be provided when profile_name is used"
            )
        if profile_name not in scoring_config.profiles:
            raise NormalizationError(f"unknown scoring profile: {profile_name}")
        profile = scoring_config.profiles[profile_name]
        profile_overrides = dict(profile.normalization_overrides)

    resolved: dict[str, NormalizationMethod] = {}
    missing_methods: list[str] = []

    for metric_id in metric_ids:
        if metric_id in resolved_overrides:
            resolved[metric_id] = resolved_overrides[metric_id]
        elif resolved_global_method is not None:
            resolved[metric_id] = resolved_global_method
        elif metric_id in profile_overrides:
            resolved[metric_id] = profile_overrides[metric_id]
        elif metrics_config is not None and metric_id in metrics_config.metrics:
            resolved[metric_id] = metrics_config.metrics[metric_id].normalization_method
        else:
            missing_methods.append(metric_id)

    if missing_methods:
        missing = ", ".join(sorted(missing_methods))
        raise NormalizationError(
            "normalization method could not be resolved for metric_id(s): " f"{missing}"
        )

    return resolved


def normalize_metric(
    df: pd.DataFrame,
    *,
    method: NormalizationMethod | str,
) -> pd.DataFrame:
    """
    Normalize a single-metric dataframe slice and append derived columns.

    The input must contain exactly one ``metric_id`` value. The raw ``value`` column is
    preserved and a new ``normalized_value`` column is appended.
    """
    _validate_normalization_input(df)

    if df.empty:
        return _append_normalization_columns(
            df,
            normalized_values=pd.Series(index=df.index, dtype="float64"),
            method=NormalizationMethod(method),
            basis=None,
        )

    metric_ids = df[METRIC_ID_COLUMN].dropna().astype("string").unique().tolist()
    if len(metric_ids) != 1:
        raise NormalizationError(
            "normalize_metric expects a single metric_id slice; "
            f"found {sorted(str(value) for value in metric_ids)}"
        )

    resolved_method = NormalizationMethod(method)
    normalized_values = _normalize_series(
        df[VALUE_COLUMN],
        method=resolved_method,
        higher_is_better=_resolve_higher_is_better(df),
    )
    return _append_normalization_columns(
        df,
        normalized_values=normalized_values,
        method=resolved_method,
        basis="metric_slice",
    )


def normalize_dataframe(
    df: pd.DataFrame,
    *,
    metrics_config: MetricsConfig | None = None,
    scoring_config: ScoringConfig | None = None,
    profile_name: str | None = None,
    method: NormalizationMethod | str | None = None,
    method_overrides: Mapping[str, NormalizationMethod | str] | None = None,
) -> pd.DataFrame:
    """
    Normalize a canonical dataframe metric-by-metric across the current filtered slice.

    The dataframe is grouped by ``metric_id`` and each group is normalized independently.
    Input is never mutated.
    """
    _validate_normalization_input(df)

    methods_by_metric = resolve_normalization_methods(
        df,
        metrics_config=metrics_config,
        scoring_config=scoring_config,
        profile_name=profile_name,
        method=method,
        method_overrides=method_overrides,
    )

    if df.empty:
        return _append_normalization_columns(
            df,
            normalized_values=pd.Series(index=df.index, dtype="float64"),
            method=None,
            basis=None,
        )

    result = df.copy(deep=True)
    result[NORMALIZED_VALUE_COLUMN] = pd.Series(index=result.index, dtype="float64")
    result[NORMALIZATION_METHOD_COLUMN] = pd.Series(index=result.index, dtype="string")
    result[NORMALIZATION_BASIS_COLUMN] = pd.Series(index=result.index, dtype="string")

    for metric_id, metric_df in df.groupby(METRIC_ID_COLUMN, sort=False, dropna=False):
        if pd.isna(metric_id):
            raise NormalizationError("metric_id contains missing values")

        resolved_method = methods_by_metric[str(metric_id)]
        normalized_values = _normalize_series(
            metric_df[VALUE_COLUMN],
            method=resolved_method,
            higher_is_better=_resolve_higher_is_better(metric_df),
        )

        result.loc[metric_df.index, NORMALIZED_VALUE_COLUMN] = normalized_values.astype(
            "float64"
        )
        result.loc[metric_df.index, NORMALIZATION_METHOD_COLUMN] = resolved_method.value
        result.loc[metric_df.index, NORMALIZATION_BASIS_COLUMN] = "metric_slice"

    result[NORMALIZATION_METHOD_COLUMN] = result[NORMALIZATION_METHOD_COLUMN].astype(
        "string"
    )
    result[NORMALIZATION_BASIS_COLUMN] = result[NORMALIZATION_BASIS_COLUMN].astype(
        "string"
    )
    return result


def _normalize_series(
    values: pd.Series,
    *,
    method: NormalizationMethod,
    higher_is_better: bool,
) -> pd.Series:
    numeric_values = pd.to_numeric(values, errors="coerce").astype("float64")

    missing_mask = numeric_values.isna()
    valid_values = numeric_values.loc[~missing_mask]

    if valid_values.empty:
        return pd.Series(np.nan, index=values.index, dtype="float64")

    if method == NormalizationMethod.MINMAX:
        normalized_valid = _minmax_normalize(valid_values)
    elif method == NormalizationMethod.PERCENTILE:
        normalized_valid = _percentile_normalize(valid_values)
    elif method == NormalizationMethod.RANK:
        normalized_valid = _rank_normalize(valid_values)
    elif method == NormalizationMethod.LOG_MINMAX:
        normalized_valid = _log_minmax_normalize(valid_values)
    else:
        raise NormalizationError(f"unsupported normalization method: {method!r}")

    if not higher_is_better:
        normalized_valid = 1.0 - normalized_valid

    normalized = pd.Series(np.nan, index=values.index, dtype="float64")
    normalized.loc[valid_values.index] = normalized_valid.astype("float64")
    return normalized.clip(lower=0.0, upper=1.0)


def _minmax_normalize(values: pd.Series) -> pd.Series:
    minimum = float(values.min())
    maximum = float(values.max())

    if maximum == minimum:
        return pd.Series(1.0, index=values.index, dtype="float64")

    return ((values - minimum) / (maximum - minimum)).astype("float64")


def _percentile_normalize(values: pd.Series) -> pd.Series:
    if len(values) == 1:
        return pd.Series(1.0, index=values.index, dtype="float64")

    ranks = values.rank(method="average", ascending=True)
    return ((ranks - 1.0) / (len(values) - 1.0)).astype("float64")


def _rank_normalize(values: pd.Series) -> pd.Series:
    if len(values) == 1:
        return pd.Series(1.0, index=values.index, dtype="float64")

    descending_ranks = values.rank(method="min", ascending=False)
    return (1.0 - ((descending_ranks - 1.0) / (len(values) - 1.0))).astype("float64")


def _log_minmax_normalize(values: pd.Series) -> pd.Series:
    if (values <= 0).any():
        raise ValueError("log-minmax normalization requires strictly positive values")

    logged = pd.Series(np.log(values.to_numpy(dtype="float64")), index=values.index)
    return _minmax_normalize(logged)


def _resolve_higher_is_better(df: pd.DataFrame) -> bool:
    _require_columns(df, [HIGHER_IS_BETTER_COLUMN])

    unique_values = [
        value
        for value in df[HIGHER_IS_BETTER_COLUMN].dropna().unique().tolist()
        if value in (True, False)
    ]
    if not unique_values:
        raise NormalizationError(
            "higher_is_better must contain a boolean value for normalization"
        )
    if len(set(unique_values)) != 1:
        raise NormalizationError(
            "higher_is_better must be consistent within each metric slice"
        )
    return bool(unique_values[0])


def _append_normalization_columns(
    df: pd.DataFrame,
    *,
    normalized_values: pd.Series,
    method: NormalizationMethod | None,
    basis: str | None,
) -> pd.DataFrame:
    result = df.copy(deep=True)
    result[NORMALIZED_VALUE_COLUMN] = normalized_values.astype("float64")
    result[NORMALIZATION_METHOD_COLUMN] = pd.Series(
        method.value if method is not None else pd.NA,
        index=result.index,
        dtype="string",
    )
    result[NORMALIZATION_BASIS_COLUMN] = pd.Series(
        basis if basis is not None else pd.NA,
        index=result.index,
        dtype="string",
    )
    return result


def _validate_normalization_input(df: pd.DataFrame) -> None:
    required_column_issues = validate_required_columns(df)
    if required_column_issues:
        issue = required_column_issues[0]
        raise NormalizationError(issue.message)

    _require_columns(df, [METRIC_ID_COLUMN, VALUE_COLUMN, HIGHER_IS_BETTER_COLUMN])


def _require_columns(df: pd.DataFrame, columns: list[str]) -> None:
    missing = [column for column in columns if column not in df.columns]
    if missing:
        raise NormalizationError(
            f"dataframe is missing required columns for normalization: {missing}"
        )
