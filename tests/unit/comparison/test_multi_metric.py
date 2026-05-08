from __future__ import annotations

import pandas as pd
import pytest

from country_compare.comparison.multi_metric import (
    ComparisonError,
    build_multi_metric_wide_table,
    compare_countries,
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
                    "democracy_index": NormalizationMethod.PERCENTILE,
                },
            )
        },
    )


def test_compare_countries_basic_multi_metric_result() -> None:
    df = build_example_metric_dataframe()

    result = compare_countries(
        df,
        metric_ids=["gdp_per_capita", "rule_of_law"],
        normalization_method=NormalizationMethod.MINMAX,
    )

    # 5 countries × 2 metrics = 10
    assert result.shape[0] == 10
    assert sorted(result["metric_id"].unique().tolist()) == [
        "gdp_per_capita",
        "rule_of_law",
    ]
    assert NORMALIZED_VALUE_COLUMN in result.columns
    assert NORMALIZATION_METHOD_COLUMN in result.columns
    assert NORMALIZATION_BASIS_COLUMN in result.columns
    assert result.groupby("metric_id")["rank"].min().to_dict() == {
        "gdp_per_capita": 1,
        "rule_of_law": 1,
    }


def test_compare_countries_common_year_selects_shared_year() -> None:
    df = build_example_metric_dataframe()

    result = compare_countries(
        df,
        metric_ids=["gdp_per_capita", "rule_of_law"],
        year_strategy=YearStrategy.COMMON_YEAR,
        normalization_method=NormalizationMethod.MINMAX,
    )

    assert result["year"].nunique() == 1
    # Latest common year is now 2025
    assert int(result["year"].iloc[0]) == 2025


def test_compare_countries_country_filters_work() -> None:
    df = build_example_metric_dataframe()

    result = compare_countries(
        df,
        metric_ids=["gdp_per_capita", "rule_of_law"],
        countries_include=["ISR", "DEU", "SGP"],
        countries_exclude=["SGP"],
        normalization_method=NormalizationMethod.MINMAX,
    )

    assert sorted(result["country_code"].unique().tolist()) == ["DEU", "ISR"]
    assert result.shape[0] == 4


def test_compare_countries_uses_metrics_config_and_overrides() -> None:
    df = build_example_metric_dataframe()

    result = compare_countries(
        df,
        metric_ids=["gdp_per_capita", "rule_of_law"],
        metrics_config=_build_metrics_config(),
        normalization_method_overrides={"rule_of_law": NormalizationMethod.MINMAX},
    )

    methods_by_metric = (
        result.groupby("metric_id")[NORMALIZATION_METHOD_COLUMN].first().to_dict()
    )
    assert methods_by_metric == {
        "gdp_per_capita": "log-minmax",
        "rule_of_law": "minmax",
    }


def test_compare_countries_can_resolve_metrics_from_profile() -> None:
    df = build_example_metric_dataframe()

    result = compare_countries(
        df,
        profile_name="governance_profile",
        scoring_config=_build_scoring_config(),
        metrics_config=_build_metrics_config(),
    )

    assert sorted(result["metric_id"].unique().tolist()) == [
        "democracy_index",
        "rule_of_law",
    ]
    methods_by_metric = (
        result.groupby("metric_id")[NORMALIZATION_METHOD_COLUMN].first().to_dict()
    )
    assert methods_by_metric == {
        "democracy_index": "percentile",
        "rule_of_law": "rank",
    }


def test_build_multi_metric_wide_table_creates_flattened_columns() -> None:
    df = build_example_metric_dataframe()
    result = compare_countries(
        df,
        metric_ids=["gdp_per_capita", "rule_of_law"],
        normalization_method=NormalizationMethod.MINMAX,
    )

    wide = build_multi_metric_wide_table(result)

    assert "gdp_per_capita__value" in wide.columns
    assert "gdp_per_capita__normalized_value" in wide.columns
    assert "gdp_per_capita__rank" in wide.columns
    assert "rule_of_law__value" in wide.columns
    # 5 countries
    assert wide.shape[0] == 5


def test_compare_countries_missing_metric_fails_clearly() -> None:
    df = build_example_metric_dataframe()

    with pytest.raises(
        ComparisonError, match="requested metric_id values were not found"
    ):
        compare_countries(
            df,
            metric_ids=["gdp_per_capita", "not_real"],
            normalization_method=NormalizationMethod.MINMAX,
        )


def test_compare_countries_duplicate_rows_fail_clearly() -> None:
    df = build_example_metric_dataframe()
    duplicate_row = df.loc[
        (df["metric_id"] == "gdp_per_capita")
        & (df["country_code"] == "ISR")
        & (df["year"] == 2025)
    ].copy()
    duplicate_df = pd.concat([df, duplicate_row], ignore_index=True)

    with pytest.raises(ComparisonError, match="duplicate rows detected"):
        compare_countries(
            duplicate_df,
            metric_ids=["gdp_per_capita", "rule_of_law"],
            normalization_method=NormalizationMethod.MINMAX,
        )


def test_compare_countries_input_immutability() -> None:
    df = build_example_metric_dataframe()
    original = df.copy(deep=True)

    _ = compare_countries(
        df,
        metric_ids=["gdp_per_capita", "rule_of_law"],
        normalization_method=NormalizationMethod.MINMAX,
    )

    pd.testing.assert_frame_equal(df, original)
    assert NORMALIZED_VALUE_COLUMN not in df.columns
    assert NORMALIZATION_METHOD_COLUMN not in df.columns
    assert "rank" not in df.columns
