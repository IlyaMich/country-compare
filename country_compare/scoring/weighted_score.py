from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass

import pandas as pd

from country_compare.comparison.multi_metric import compare_countries
from country_compare.comparison.single_metric import ComparisonError
from country_compare.config.models import (
    MetricsConfig,
    MissingDataPolicy,
    NormalizationMethod,
    ScoringConfig,
    YearStrategy,
)
from country_compare.config.validator import (
    ConfigurationValidationError,
    resolve_profile_options,
    resolve_profile_weights,
)
from country_compare.metrics.normalization import NORMALIZED_VALUE_COLUMN

COUNTRY_CODE_COLUMN = "country_code"
COUNTRY_NAME_COLUMN = "country_name"
METRIC_ID_COLUMN = "metric_id"
WEIGHTED_SCORE_COLUMN = "weighted_score"
SCORE_RANK_COLUMN = "score_rank"
SCORE_RANK_METHOD_COLUMN = "score_rank_method"
MISSING_METRICS_COLUMN = "missing_metrics"
METRIC_COUNT_USED_COLUMN = "metric_count_used"
METRIC_COUNT_EXPECTED_COLUMN = "metric_count_expected"
MISSING_METRIC_COUNT_COLUMN = "missing_metric_count"
WEIGHT_SUM_USED_COLUMN = "weight_sum_used"
PROFILE_NAME_COLUMN = "profile_name"
MISSING_DATA_POLICY_COLUMN = "missing_data_policy"
YEAR_STRATEGY_COLUMN = "year_strategy"
DEFAULT_COUNTRY_METADATA_COLUMNS: tuple[str, ...] = (
    COUNTRY_CODE_COLUMN,
    COUNTRY_NAME_COLUMN,
    "region",
    "income_group",
)
DEFAULT_SCORE_RANK_METHOD = "competition_min"


class ScoringError(ValueError):
    """Raised when weighted scoring cannot be completed."""


@dataclass(frozen=True)
class ResolvedScoringProfile:
    profile_name: str
    weights: dict[str, float]
    year_strategy: YearStrategy
    missing_data_policy: MissingDataPolicy


def resolve_scoring_profile(
    metrics_config: MetricsConfig,
    scoring_config: ScoringConfig,
    *,
    profile_name: str | None = None,
) -> ResolvedScoringProfile:
    """
    Resolve scoring behavior from config helpers without re-implementing profile logic.
    """
    selected_profile_name = profile_name or scoring_config.default_profile

    try:
        weights = resolve_profile_weights(
            metrics_config,
            scoring_config,
            selected_profile_name,
        )
        options = resolve_profile_options(scoring_config, selected_profile_name)
    except ConfigurationValidationError as exc:
        raise ScoringError(str(exc)) from exc

    return ResolvedScoringProfile(
        profile_name=selected_profile_name,
        weights=dict(weights),
        year_strategy=YearStrategy(options["year_strategy"]),
        missing_data_policy=MissingDataPolicy(options["missing_data_policy"]),
    )


def prepare_weighted_score_input(
    dataframe: pd.DataFrame,
    *,
    metrics_config: MetricsConfig,
    scoring_config: ScoringConfig,
    profile_name: str | None = None,
    countries_include: Iterable[str] | None = None,
    countries_exclude: Iterable[str] | None = None,
    target_year: int | None = None,
    normalization_method: NormalizationMethod | str | None = None,
    normalization_method_overrides: (
        Mapping[str, NormalizationMethod | str] | None
    ) = None,
) -> pd.DataFrame:
    """
    Build the filtered and normalized long-form input used by weighted scoring.

    This reuses:
    - profile metric selection from config
    - profile year strategy from config
    - multi-metric comparison for filtering + normalization + per-metric ranking
    """
    resolved_profile = resolve_scoring_profile(
        metrics_config,
        scoring_config,
        profile_name=profile_name,
    )

    try:
        prepared = compare_countries(
            dataframe,
            countries_include=countries_include,
            countries_exclude=countries_exclude,
            year_strategy=resolved_profile.year_strategy,
            target_year=target_year,
            normalization_method=normalization_method,
            normalization_method_overrides=normalization_method_overrides,
            metrics_config=metrics_config,
            scoring_config=scoring_config,
            profile_name=resolved_profile.profile_name,
        )
    except ComparisonError as exc:
        raise ScoringError(str(exc)) from exc

    return prepared.copy(deep=True)


def compute_weighted_scores(
    dataframe: pd.DataFrame,
    *,
    weights: Mapping[str, float],
    missing_data_policy: MissingDataPolicy | str,
) -> pd.DataFrame:
    """
    Aggregate normalized metric rows into one weighted score per country.

    Parameters
    ----------
    dataframe:
        Filtered and normalized long-form dataframe. Expected to contain one row per
        country + metric for the scoring slice.
    weights:
        Resolved metric weights keyed by metric_id.
    missing_data_policy:
        ``renormalize_weights`` keeps partial countries by renormalizing over present
        metrics. ``drop_country`` excludes countries missing any expected metric.
    """
    resolved_policy = MissingDataPolicy(missing_data_policy)
    resolved_weights = _validate_weights(weights)
    _require_columns(
        dataframe, [COUNTRY_CODE_COLUMN, METRIC_ID_COLUMN, NORMALIZED_VALUE_COLUMN]
    )

    relevant = dataframe.loc[
        dataframe[METRIC_ID_COLUMN].astype("string").isin(resolved_weights.keys())
    ].copy()

    if relevant.empty:
        raise ScoringError(
            "no rows remain after restricting data to the weighted metrics"
        )

    duplicate_pairs = relevant.duplicated(
        subset=[COUNTRY_CODE_COLUMN, METRIC_ID_COLUMN], keep=False
    )
    if duplicate_pairs.any():
        duplicate_rows = relevant.loc[
            duplicate_pairs,
            [COUNTRY_CODE_COLUMN, METRIC_ID_COLUMN],
        ]
        raise ScoringError(
            "weighted scoring requires at most one row per country + metric in the input. "
            f"Duplicates={duplicate_rows.to_dict(orient='records')}"
        )

    expected_metrics = list(resolved_weights.keys())
    score_rows: list[dict[str, object]] = []

    for _country_code, country_df in relevant.groupby(
        COUNTRY_CODE_COLUMN, sort=False, dropna=False
    ):
        available_metrics = set(
            country_df.loc[
                country_df[NORMALIZED_VALUE_COLUMN].notna(), METRIC_ID_COLUMN
            ]
            .astype("string")
            .tolist()
        )
        missing_metrics = [
            metric_id
            for metric_id in expected_metrics
            if metric_id not in available_metrics
        ]

        if resolved_policy == MissingDataPolicy.DROP_COUNTRY and missing_metrics:
            continue

        country_weights = {
            metric_id: weight
            for metric_id, weight in resolved_weights.items()
            if metric_id in available_metrics
        }
        if not country_weights:
            continue

        if resolved_policy == MissingDataPolicy.RENORMALIZE_WEIGHTS and missing_metrics:
            denominator = sum(country_weights.values())
            if denominator <= 0:
                continue
            effective_weights = {
                metric_id: weight / denominator
                for metric_id, weight in country_weights.items()
            }
        else:
            effective_weights = dict(country_weights)

        metric_values = (
            country_df[[METRIC_ID_COLUMN, NORMALIZED_VALUE_COLUMN]]
            .dropna(subset=[NORMALIZED_VALUE_COLUMN])
            .drop_duplicates(subset=[METRIC_ID_COLUMN])
            .set_index(METRIC_ID_COLUMN)[NORMALIZED_VALUE_COLUMN]
        )

        score = 0.0
        for metric_id, effective_weight in effective_weights.items():
            score += float(metric_values.loc[metric_id]) * float(effective_weight)

        row = _extract_country_metadata(country_df)
        row[WEIGHTED_SCORE_COLUMN] = float(score)
        row[METRIC_COUNT_USED_COLUMN] = len(effective_weights)
        row[METRIC_COUNT_EXPECTED_COLUMN] = len(expected_metrics)
        row[MISSING_METRIC_COUNT_COLUMN] = len(missing_metrics)
        row[MISSING_METRICS_COLUMN] = (
            ", ".join(missing_metrics) if missing_metrics else pd.NA
        )
        row[WEIGHT_SUM_USED_COLUMN] = float(sum(effective_weights.values()))
        row[MISSING_DATA_POLICY_COLUMN] = resolved_policy.value
        score_rows.append(row)

    if not score_rows:
        raise ScoringError(
            "no countries could be scored under the requested missing-data policy"
        )

    result = pd.DataFrame(score_rows)
    result = _rank_weighted_scores(result)
    return result


def score_countries(
    dataframe: pd.DataFrame,
    *,
    metrics_config: MetricsConfig,
    scoring_config: ScoringConfig,
    profile_name: str | None = None,
    countries_include: Iterable[str] | None = None,
    countries_exclude: Iterable[str] | None = None,
    target_year: int | None = None,
    normalization_method: NormalizationMethod | str | None = None,
    normalization_method_overrides: (
        Mapping[str, NormalizationMethod | str] | None
    ) = None,
) -> pd.DataFrame:
    """
    End-to-end Phase 9 weighted scoring workflow.

    This function deliberately delegates profile behavior to config helpers:
    - metrics and weights via ``resolve_profile_weights``
    - year strategy and missing-data policy via ``resolve_profile_options``
    """
    resolved_profile = resolve_scoring_profile(
        metrics_config,
        scoring_config,
        profile_name=profile_name,
    )

    prepared = prepare_weighted_score_input(
        dataframe,
        metrics_config=metrics_config,
        scoring_config=scoring_config,
        profile_name=resolved_profile.profile_name,
        countries_include=countries_include,
        countries_exclude=countries_exclude,
        target_year=target_year,
        normalization_method=normalization_method,
        normalization_method_overrides=normalization_method_overrides,
    )

    scored = compute_weighted_scores(
        prepared,
        weights=resolved_profile.weights,
        missing_data_policy=resolved_profile.missing_data_policy,
    )
    scored = scored.copy(deep=True)
    scored[PROFILE_NAME_COLUMN] = pd.Series(
        resolved_profile.profile_name,
        index=scored.index,
        dtype="string",
    )
    scored[YEAR_STRATEGY_COLUMN] = pd.Series(
        resolved_profile.year_strategy.value,
        index=scored.index,
        dtype="string",
    )
    return scored


def _validate_weights(weights: Mapping[str, float]) -> dict[str, float]:
    if not weights:
        raise ScoringError("weights must not be empty")

    resolved: dict[str, float] = {}
    for metric_id, weight in weights.items():
        key = str(metric_id).strip()
        value = float(weight)
        if not key:
            raise ScoringError("weight metric_id must not be empty")
        if value <= 0:
            raise ScoringError(f"weight for metric '{key}' must be > 0")
        resolved[key] = value
    return resolved


def _extract_country_metadata(dataframe: pd.DataFrame) -> dict[str, object]:
    row: dict[str, object] = {}
    for column in DEFAULT_COUNTRY_METADATA_COLUMNS:
        if column not in dataframe.columns:
            continue
        non_null_values = dataframe[column].dropna()
        row[column] = non_null_values.iloc[0] if not non_null_values.empty else pd.NA
    return row


def _rank_weighted_scores(dataframe: pd.DataFrame) -> pd.DataFrame:
    result = dataframe.copy(deep=True)
    result[SCORE_RANK_COLUMN] = (
        result[WEIGHTED_SCORE_COLUMN]
        .rank(method="min", ascending=False)
        .astype("Int64")
    )
    result[SCORE_RANK_METHOD_COLUMN] = pd.Series(
        DEFAULT_SCORE_RANK_METHOD,
        index=result.index,
        dtype="string",
    )

    sort_columns = [
        SCORE_RANK_COLUMN,
        *(
            column
            for column in [COUNTRY_NAME_COLUMN, COUNTRY_CODE_COLUMN]
            if column in result.columns
        ),
    ]
    result = result.sort_values(
        by=sort_columns,
        ascending=[True] * len(sort_columns),
        kind="mergesort",
        na_position="last",
    ).reset_index(drop=True)
    return result


def _require_columns(dataframe: pd.DataFrame, columns: Sequence[str]) -> None:
    missing = [column for column in columns if column not in dataframe.columns]
    if missing:
        raise ScoringError(
            f"dataframe is missing required columns for weighted scoring: {missing}"
        )


__all__ = [
    "WEIGHTED_SCORE_COLUMN",
    "SCORE_RANK_COLUMN",
    "SCORE_RANK_METHOD_COLUMN",
    "MISSING_METRICS_COLUMN",
    "METRIC_COUNT_USED_COLUMN",
    "METRIC_COUNT_EXPECTED_COLUMN",
    "MISSING_METRIC_COUNT_COLUMN",
    "WEIGHT_SUM_USED_COLUMN",
    "PROFILE_NAME_COLUMN",
    "MISSING_DATA_POLICY_COLUMN",
    "YEAR_STRATEGY_COLUMN",
    "ScoringError",
    "ResolvedScoringProfile",
    "resolve_scoring_profile",
    "prepare_weighted_score_input",
    "compute_weighted_scores",
    "score_countries",
]
