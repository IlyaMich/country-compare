from __future__ import annotations

import pandas as pd
import pytest

from country_compare.comparison.single_metric import (
    ComparisonError,
    RANK_COLUMN,
    RANK_METHOD_COLUMN,
    compare_metric,
)
from country_compare.config.models import (
    MetricConfig,
    MetricsConfig,
    NormalizationMethod,
    ScoringConfig,
    ScoringProfile,
    WeightHandlingStrategy,
    YearStrategy,
)
from country_compare.data.examples import build_example_metric_dataframe
from country_compare.metrics.normalization import (
    NORMALIZATION_BASIS_COLUMN,
    NORMALIZATION_METHOD_COLUMN,
    NORMALIZED_VALUE_COLUMN,
)


def _build_metrics_config() -> MetricsConfig:
    return MetricsConfig(
        metrics={
            "gdp_per_capita": MetricConfig(
                display_name="GDP per capita",
                category="economy",
                higher_is_better=True,
                default_weight=1.0,
                unit="USD",
                normalization_method=NormalizationMethod.LOG_MINMAX,
            ),
            "rule_of_law": MetricConfig(
                display_name="Rule of Law",
                category="governance",
                higher_is_better=True,
                default_weight=1.0,
                unit="index",
                normalization_method=NormalizationMethod.PERCENTILE,
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
        default_profile="governance_profile",
        weight_handling=WeightHandlingStrategy.NORMALIZE,
        default_year_strategy=YearStrategy.LATEST_PER_METRIC,
        profiles={
            "governance_profile": ScoringProfile(
                metrics=["rule_of_law", "democracy_index"],
                normalization_overrides={
                    "rule_of_law": NormalizationMethod.RANK,
                },
            )
        },
    )


def test_compare_metric_basic_ranking_order() -> None:
    df = build_example_metric_dataframe()

    result = compare_metric(
        df,
        metric_id="gdp_per_capita",
        normalization_method=NormalizationMethod.MINMAX,
    )

    # 5 countries, descending order by gdp_per_capita 2023
    expected_order = ["SGP", "DEU", "CAN", "ISR", "JPN"]
    assert result["country_code"].tolist() == expected_order
    assert result[RANK_COLUMN].tolist() == [1, 2, 3, 4, 5]
    assert result[NORMALIZATION_METHOD_COLUMN].tolist() == ["minmax"] * 5
    assert result[NORMALIZATION_BASIS_COLUMN].tolist() == ["metric_slice"] * 5
    assert result[RANK_METHOD_COLUMN].tolist() == ["competition_min"] * 5
    assert result["year"].tolist() == [2025] * 5


def test_compare_metric_uses_target_year() -> None:
    df = build_example_metric_dataframe()

    result = compare_metric(
        df,
        metric_id="gdp_per_capita",
        year_strategy=YearStrategy.TARGET_YEAR,
        target_year=2022,
        normalization_method=NormalizationMethod.MINMAX,
    )

    assert result["year"].nunique() == 1
    assert int(result["year"].iloc[0]) == 2022
    # 5 countries, descending order by gdp_per_capita 2022
    expected_order = ["SGP", "DEU", "CAN", "ISR", "JPN"]
    assert result["country_code"].tolist() == expected_order


def test_compare_metric_country_include_exclude() -> None:
    df = build_example_metric_dataframe()

    result = compare_metric(
        df,
        metric_id="gdp_per_capita",
        countries_include=["ISR", "DEU", "SGP"],
        countries_exclude=["SGP"],
        normalization_method=NormalizationMethod.MINMAX,
    )

    assert result["country_code"].tolist() == ["DEU", "ISR"]
    assert result[RANK_COLUMN].tolist() == [1, 2]


def test_compare_metric_uses_metrics_config_for_normalization_resolution() -> None:
    df = build_example_metric_dataframe()

    result = compare_metric(
        df,
        metric_id="gdp_per_capita",
        metrics_config=_build_metrics_config(),
    )

    assert result[NORMALIZATION_METHOD_COLUMN].tolist() == ["log-minmax"] * 5


def test_compare_metric_explicit_normalization_override_wins() -> None:
    df = build_example_metric_dataframe()

    result = compare_metric(
        df,
        metric_id="gdp_per_capita",
        metrics_config=_build_metrics_config(),
        normalization_method=NormalizationMethod.PERCENTILE,
    )

    assert result[NORMALIZATION_METHOD_COLUMN].tolist() == ["percentile"] * 5
    assert set(result[RANK_COLUMN]) == {1, 2, 3, 4, 5}


def test_compare_metric_profile_override_is_used_when_no_explicit_method() -> None:
    df = build_example_metric_dataframe()

    result = compare_metric(
        df,
        metric_id="rule_of_law",
        metrics_config=_build_metrics_config(),
        scoring_config=_build_scoring_config(),
        profile_name="governance_profile",
    )

    assert result[NORMALIZATION_METHOD_COLUMN].tolist() == ["rank"] * 5
    assert set(result[RANK_COLUMN]) == {1, 2, 3, 4, 5}
    assert set(result["country_code"]) == {"ISR", "DEU", "SGP", "CAN", "JPN"}


def test_compare_metric_ties_get_same_rank_and_deterministic_order() -> None:
    df = build_example_metric_dataframe()
    tied = df.loc[
        (df["metric_id"] == "rule_of_law") & (df["year"] == 2022),
        :,
    ].copy()
    tied.loc[:, "value"] = 10.0

    result = compare_metric(
        tied,
        metric_id="rule_of_law",
        normalization_method=NormalizationMethod.MINMAX,
    )

    # All tied, so all should have rank 1 and normalized value 1.0
    assert set(result[RANK_COLUMN]) == {1}
    assert set(result[NORMALIZED_VALUE_COLUMN]) == {1.0}


def test_compare_metric_single_country_behavior() -> None:
    df = build_example_metric_dataframe()

    result = compare_metric(
        df,
        metric_id="gdp_per_capita",
        countries_include=["ISR"],
        normalization_method=NormalizationMethod.MINMAX,
    )

    assert result.shape[0] == 1
    assert result["country_code"].tolist() == ["ISR"]
    assert result[NORMALIZED_VALUE_COLUMN].tolist() == pytest.approx([1.0])
    assert result[RANK_COLUMN].tolist() == [1]


def test_compare_metric_metric_not_found_failure() -> None:
    df = build_example_metric_dataframe()

    with pytest.raises(ComparisonError, match="metric_id 'nonexistent_metric' was not found"):
        compare_metric(
            df,
            metric_id="nonexistent_metric",
            normalization_method=NormalizationMethod.MINMAX,
        )


def test_compare_metric_input_immutability() -> None:
    df = build_example_metric_dataframe()
    original = df.copy(deep=True)

    _ = compare_metric(
        df,
        metric_id="gdp_per_capita",
        normalization_method=NormalizationMethod.MINMAX,
    )

    pd.testing.assert_frame_equal(df, original)
    assert NORMALIZED_VALUE_COLUMN not in df.columns
    assert NORMALIZATION_METHOD_COLUMN not in df.columns
    assert RANK_COLUMN not in df.columns


def test_compare_metric_preserves_canonical_columns_plus_derived_columns() -> None:
    df = build_example_metric_dataframe()

    result = compare_metric(
        df,
        metric_id="gdp_per_capita",
        normalization_method=NormalizationMethod.MINMAX,
    )

    expected_columns = [
        "country_code",
        "country_name",
        "metric_id",
        "metric_name",
        "value",
        "year",
        "unit",
        "source_name",
        "source_url",
        "higher_is_better",
        "category",
        "dataset_version",
        "region",
        "income_group",
        "notes",
        NORMALIZED_VALUE_COLUMN,
        NORMALIZATION_METHOD_COLUMN,
        NORMALIZATION_BASIS_COLUMN,
        RANK_COLUMN,
        RANK_METHOD_COLUMN,
    ]
    assert result.columns.tolist() == expected_columns


def test_compare_metric_duplicate_country_rows_fail_clearly() -> None:
    df = build_example_metric_dataframe()
    duplicate_row = df.loc[
        (df["metric_id"] == "gdp_per_capita")
        & (df["country_code"] == "ISR")
        & (df["year"] == 2025)
    ].copy()
    duplicate_df = pd.concat([df, duplicate_row], ignore_index=True)

    with pytest.raises(ComparisonError, match="duplicate rows detected"):
        compare_metric(
            duplicate_df,
            metric_id="gdp_per_capita",
            normalization_method=NormalizationMethod.MINMAX,
        )
