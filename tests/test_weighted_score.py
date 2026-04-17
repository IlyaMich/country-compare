from __future__ import annotations

import pandas as pd
import pytest

from country_compare.metrics.normalization import NORMALIZED_VALUE_COLUMN
from country_compare.scoring.weighted_score import (
    METRIC_COUNT_EXPECTED_COLUMN,
    METRIC_COUNT_USED_COLUMN,
    MISSING_DATA_POLICY_COLUMN,
    MISSING_METRICS_COLUMN,
    PROFILE_NAME_COLUMN,
    SCORE_RANK_COLUMN,
    WEIGHT_SUM_USED_COLUMN,
    WEIGHTED_SCORE_COLUMN,
    compute_weighted_scores,
    prepare_weighted_score_input,
    resolve_scoring_profile,
    score_countries,
)
from country_compare.config.models import (
    MetricConfig,
    MetricsConfig,
    MissingDataPolicy,
    NormalizationMethod,
    ScoringConfig,
    ScoringProfile,
    WeightHandlingStrategy,
    YearStrategy,
)
from country_compare.data.examples import build_example_metric_dataframe


def _build_metrics_config() -> MetricsConfig:
    return MetricsConfig(
        metrics={
            "gdp_per_capita": MetricConfig(
                display_name="GDP per capita",
                category="economy",
                higher_is_better=True,
                default_weight=2.0,
                unit="USD",
                normalization_method=NormalizationMethod.MINMAX,
            ),
            "rule_of_law": MetricConfig(
                display_name="Rule of Law",
                category="governance",
                higher_is_better=True,
                default_weight=1.0,
                unit="index",
                normalization_method=NormalizationMethod.MINMAX,
            ),
            "democracy_index": MetricConfig(
                display_name="Democracy Index",
                category="governance",
                higher_is_better=True,
                default_weight=1.0,
                unit="score_0_10",
                normalization_method=NormalizationMethod.MINMAX,
            ),
        }
    )


def _build_scoring_config() -> ScoringConfig:
    return ScoringConfig(
        default_profile="core",
        weight_handling=WeightHandlingStrategy.NORMALIZE,
        default_year_strategy=YearStrategy.LATEST_PER_METRIC,
        default_missing_data_policy=MissingDataPolicy.RENORMALIZE_WEIGHTS,
        profiles={
            "core": ScoringProfile(
                metrics=["gdp_per_capita", "rule_of_law"],
                weights={"gdp_per_capita": 3.0, "rule_of_law": 1.0},
                normalization_overrides={
                    "gdp_per_capita": NormalizationMethod.MINMAX,
                    "rule_of_law": NormalizationMethod.MINMAX,
                },
                year_strategy=YearStrategy.COMMON_YEAR,
                missing_data_policy=MissingDataPolicy.RENORMALIZE_WEIGHTS,
            ),
            "drop_partial": ScoringProfile(
                metrics=["gdp_per_capita", "democracy_index"],
                weights={"gdp_per_capita": 1.0, "democracy_index": 1.0},
                normalization_overrides={
                    "gdp_per_capita": NormalizationMethod.MINMAX,
                    "democracy_index": NormalizationMethod.MINMAX,
                },
                year_strategy=YearStrategy.LATEST_PER_METRIC,
                missing_data_policy=MissingDataPolicy.DROP_COUNTRY,
            ),
        },
    )


def test_resolve_scoring_profile_uses_config_resolution() -> None:
    resolved = resolve_scoring_profile(
        _build_metrics_config(),
        _build_scoring_config(),
        profile_name="core",
    )

    assert resolved.profile_name == "core"
    assert resolved.year_strategy == YearStrategy.COMMON_YEAR
    assert resolved.missing_data_policy == MissingDataPolicy.RENORMALIZE_WEIGHTS
    assert resolved.weights == {"gdp_per_capita": 0.75, "rule_of_law": 0.25}


def test_prepare_weighted_score_input_uses_profile_year_strategy() -> None:
    df = build_example_metric_dataframe()

    prepared = prepare_weighted_score_input(
        df,
        metrics_config=_build_metrics_config(),
        scoring_config=_build_scoring_config(),
        profile_name="core",
    )

    assert prepared["year"].nunique() == 1
    assert int(prepared["year"].iloc[0]) == 2022
    assert sorted(prepared["metric_id"].unique().tolist()) == ["gdp_per_capita", "rule_of_law"]


def test_score_countries_basic_weighted_result() -> None:
    df = build_example_metric_dataframe()

    scored = score_countries(
        df,
        metrics_config=_build_metrics_config(),
        scoring_config=_build_scoring_config(),
        profile_name="core",
    )

    assert scored["country_code"].tolist() == ["SGP", "DEU", "ISR"]
    assert scored[SCORE_RANK_COLUMN].tolist() == [1, 2, 3]
    assert scored[PROFILE_NAME_COLUMN].tolist() == ["core", "core", "core"]
    assert scored[MISSING_DATA_POLICY_COLUMN].tolist() == [
        "renormalize_weights",
        "renormalize_weights",
        "renormalize_weights",
    ]
    assert scored[WEIGHTED_SCORE_COLUMN].tolist() == pytest.approx([
        0.9852941176470589,
        0.34593023255813954,
        0.0,
    ])


def test_compute_weighted_scores_renormalizes_for_partial_country() -> None:
    df = build_example_metric_dataframe()
    partial = df.loc[~((df["country_code"] == "SGP") & (df["metric_id"] == "democracy_index"))].copy()

    prepared = prepare_weighted_score_input(
        partial,
        metrics_config=_build_metrics_config(),
        scoring_config=_build_scoring_config(),
        profile_name="drop_partial",
    )

    scored = compute_weighted_scores(
        prepared,
        weights={"gdp_per_capita": 0.5, "democracy_index": 0.5},
        missing_data_policy=MissingDataPolicy.RENORMALIZE_WEIGHTS,
    )

    sgp_row = scored.loc[scored["country_code"] == "SGP"].iloc[0]
    assert float(sgp_row[WEIGHTED_SCORE_COLUMN]) == pytest.approx(1.0)
    assert int(sgp_row[METRIC_COUNT_USED_COLUMN]) == 1
    assert int(sgp_row[METRIC_COUNT_EXPECTED_COLUMN]) == 2
    assert str(sgp_row[MISSING_METRICS_COLUMN]) == "democracy_index"
    assert float(sgp_row[WEIGHT_SUM_USED_COLUMN]) == pytest.approx(1.0)


def test_score_countries_drop_country_policy_excludes_partial_country() -> None:
    df = build_example_metric_dataframe()
    partial = df.loc[~((df["country_code"] == "SGP") & (df["metric_id"] == "democracy_index"))].copy()

    scored = score_countries(
        partial,
        metrics_config=_build_metrics_config(),
        scoring_config=_build_scoring_config(),
        profile_name="drop_partial",
    )

    assert scored["country_code"].tolist() == ["DEU", "ISR"]
    assert scored[SCORE_RANK_COLUMN].tolist() == [1, 2]


def test_compute_weighted_scores_requires_normalized_values() -> None:
    df = build_example_metric_dataframe().loc[
        lambda frame: frame["metric_id"].isin(["gdp_per_capita", "rule_of_law"])
    ].copy()

    with pytest.raises(ValueError, match="missing required columns"):
        compute_weighted_scores(
            df,
            weights={"gdp_per_capita": 0.5, "rule_of_law": 0.5},
            missing_data_policy=MissingDataPolicy.RENORMALIZE_WEIGHTS,
        )


def test_score_countries_input_immutability() -> None:
    df = build_example_metric_dataframe()
    original = df.copy(deep=True)

    _ = score_countries(
        df,
        metrics_config=_build_metrics_config(),
        scoring_config=_build_scoring_config(),
        profile_name="core",
    )

    pd.testing.assert_frame_equal(df, original)
    assert NORMALIZED_VALUE_COLUMN not in df.columns
