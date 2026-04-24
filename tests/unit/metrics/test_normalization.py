import pandas as pd
import pytest

from country_compare.config.models import (
    MetricConfig,
    MetricsConfig,
    NormalizationMethod,
    ScoringConfig,
    ScoringProfile,
)
from country_compare.data.examples import build_example_metric_dataframe
from country_compare.metrics.normalization import (
    NORMALIZATION_BASIS_COLUMN,
    NORMALIZATION_METHOD_COLUMN,
    NORMALIZED_VALUE_COLUMN,
    normalize_dataframe,
    normalize_metric,
    resolve_normalization_methods,
)


def _build_inflation_df() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "country_code": "ISR",
                "country_name": "Israel",
                "metric_id": "inflation",
                "metric_name": "Inflation",
                "value": 4.0,
                "year": 2023,
                "unit": "percent",
                "source_name": "Example Source",
                "source_url": "https://example.org/inflation",
                "higher_is_better": False,
                "category": "economy",
                "dataset_version": "v0.1.0",
                "region": "Middle East",
                "income_group": "High income",
                "notes": None,
            },
            {
                "country_code": "DEU",
                "country_name": "Germany",
                "metric_id": "inflation",
                "metric_name": "Inflation",
                "value": 2.0,
                "year": 2023,
                "unit": "percent",
                "source_name": "Example Source",
                "source_url": "https://example.org/inflation",
                "higher_is_better": False,
                "category": "economy",
                "dataset_version": "v0.1.0",
                "region": "Europe",
                "income_group": "High income",
                "notes": None,
            },
            {
                "country_code": "SGP",
                "country_name": "Singapore",
                "metric_id": "inflation",
                "metric_name": "Inflation",
                "value": 1.0,
                "year": 2023,
                "unit": "percent",
                "source_name": "Example Source",
                "source_url": "https://example.org/inflation",
                "higher_is_better": False,
                "category": "economy",
                "dataset_version": "v0.1.0",
                "region": "Asia",
                "income_group": "High income",
                "notes": None,
            },
        ]
    )


def test_minmax_normalization_single_metric_slice():
    df = build_example_metric_dataframe()
    gdp = df.loc[(df["metric_id"] == "gdp_per_capita") & (df["year"] == 2022)].copy()

    result = normalize_metric(gdp, method="minmax")

    assert NORMALIZED_VALUE_COLUMN in result.columns
    assert NORMALIZATION_METHOD_COLUMN in result.columns
    assert NORMALIZATION_BASIS_COLUMN in result.columns
    # For 2022: ISR=54000, DEU=65000, SGP=140000, CAN=59000, JPN=42000
    min_val = 42000.0
    max_val = 140000.0
    expected = {
        "ISR": (54000.0 - min_val) / (max_val - min_val),
        "DEU": (65000.0 - min_val) / (max_val - min_val),
        "SGP": (140000.0 - min_val) / (max_val - min_val),
        "CAN": (59000.0 - min_val) / (max_val - min_val),
        "JPN": (42000.0 - min_val) / (max_val - min_val),
    }
    for code, val in expected.items():
        assert result.loc[result["country_code"] == code, NORMALIZED_VALUE_COLUMN].iloc[
            0
        ] == pytest.approx(val)


def test_percentile_normalization_produces_zero_to_one_scale():
    df = build_example_metric_dataframe()
    rule = df.loc[df["metric_id"] == "rule_of_law"].copy()

    result = normalize_metric(rule, method="percentile")

    values = result.set_index("country_code")[NORMALIZED_VALUE_COLUMN].to_dict()
    # For 5 countries, percentiles: lowest=0.0, highest=1.0, others in between
    assert min(values.values()) == pytest.approx(0.0)
    assert max(values.values()) == pytest.approx(1.0)
    # All values should be between 0 and 1
    for v in values.values():
        assert 0.0 <= v <= 1.0


def test_rank_normalization_respects_lower_is_better():
    df = _build_inflation_df()

    result = normalize_metric(df, method="rank")

    values = result.set_index("country_code")[NORMALIZED_VALUE_COLUMN].to_dict()
    assert values["SGP"] == pytest.approx(1.0)
    assert values["DEU"] == pytest.approx(0.5)
    assert values["ISR"] == pytest.approx(0.0)


def test_log_minmax_normalization_works_for_positive_values():
    df = build_example_metric_dataframe()
    gdp = df.loc[(df["metric_id"] == "gdp_per_capita") & (df["year"] == 2022)].copy()

    result = normalize_metric(gdp, method=NormalizationMethod.LOG_MINMAX)

    values = result[NORMALIZED_VALUE_COLUMN]
    assert values.min() >= 0.0
    assert values.max() <= 1.0
    assert result.loc[result["country_code"] == "SGP", NORMALIZED_VALUE_COLUMN].iloc[
        0
    ] == pytest.approx(1.0)


def test_zero_variance_minmax_returns_all_ones():
    df = (
        build_example_metric_dataframe()
        .loc[lambda frame: (frame["metric_id"] == "rule_of_law")]
        .copy()
    )
    df["value"] = 5.0

    result = normalize_metric(df, method="minmax")

    # Should be all ones, length = 10 (5 countries × 2 years)
    assert result[NORMALIZED_VALUE_COLUMN].tolist() == [1.0] * len(result)


def test_input_dataframe_is_not_mutated():
    df = build_example_metric_dataframe()
    original = df.copy(deep=True)

    _ = normalize_dataframe(df, method="minmax")

    pd.testing.assert_frame_equal(df, original)
    assert NORMALIZED_VALUE_COLUMN not in df.columns


def test_normalization_preserves_canonical_columns_and_order():
    df = build_example_metric_dataframe()
    original_columns = list(df.columns)

    result = normalize_dataframe(df, method="minmax")

    assert result.columns[: len(original_columns)].tolist() == original_columns
    pd.testing.assert_series_equal(result["country_code"], df["country_code"])
    assert str(result["country_code"].dtype) == str(df["country_code"].dtype)
    assert str(result["year"].dtype) == str(df["year"].dtype)


def test_resolve_normalization_methods_uses_metric_defaults():
    df = (
        build_example_metric_dataframe()
        .loc[lambda frame: frame["metric_id"].isin(["gdp_per_capita", "rule_of_law"])]
        .copy()
    )
    metrics_config = MetricsConfig(
        metrics={
            "gdp_per_capita": MetricConfig(
                display_name="GDP per capita",
                category="economy",
                higher_is_better=True,
                default_weight=1.0,
                normalization_method=NormalizationMethod.LOG_MINMAX,
            ),
            "rule_of_law": MetricConfig(
                display_name="Rule of Law",
                category="governance",
                higher_is_better=True,
                default_weight=1.0,
                normalization_method=NormalizationMethod.MINMAX,
            ),
        }
    )

    resolved = resolve_normalization_methods(df, metrics_config=metrics_config)

    assert resolved == {
        "gdp_per_capita": NormalizationMethod.LOG_MINMAX,
        "rule_of_law": NormalizationMethod.MINMAX,
    }


def test_profile_override_behavior_takes_precedence_over_metric_default():
    df = (
        build_example_metric_dataframe()
        .loc[lambda frame: frame["metric_id"].isin(["gdp_per_capita", "rule_of_law"])]
        .copy()
    )
    metrics_config = MetricsConfig(
        metrics={
            "gdp_per_capita": MetricConfig(
                display_name="GDP per capita",
                category="economy",
                higher_is_better=True,
                default_weight=1.0,
                normalization_method=NormalizationMethod.MINMAX,
            ),
            "rule_of_law": MetricConfig(
                display_name="Rule of Law",
                category="governance",
                higher_is_better=True,
                default_weight=1.0,
                normalization_method=NormalizationMethod.MINMAX,
            ),
        }
    )
    scoring_config = ScoringConfig(
        default_profile="default",
        profiles={
            "default": ScoringProfile(
                metrics=["gdp_per_capita", "rule_of_law"],
                normalization_overrides={
                    "gdp_per_capita": NormalizationMethod.LOG_MINMAX,
                },
            )
        },
    )

    result = normalize_dataframe(
        df,
        metrics_config=metrics_config,
        scoring_config=scoring_config,
        profile_name="default",
    )

    methods = result.groupby("metric_id")[NORMALIZATION_METHOD_COLUMN].first().to_dict()
    assert methods["gdp_per_capita"] == "log-minmax"
    assert methods["rule_of_law"] == "minmax"


def test_explicit_method_overrides_profile_and_defaults():
    df = (
        build_example_metric_dataframe()
        .loc[lambda frame: frame["metric_id"].isin(["gdp_per_capita", "rule_of_law"])]
        .copy()
    )
    metrics_config = MetricsConfig(
        metrics={
            "gdp_per_capita": MetricConfig(
                display_name="GDP per capita",
                category="economy",
                higher_is_better=True,
                default_weight=1.0,
                normalization_method=NormalizationMethod.LOG_MINMAX,
            ),
            "rule_of_law": MetricConfig(
                display_name="Rule of Law",
                category="governance",
                higher_is_better=True,
                default_weight=1.0,
                normalization_method=NormalizationMethod.PERCENTILE,
            ),
        }
    )
    scoring_config = ScoringConfig(
        default_profile="default",
        profiles={
            "default": ScoringProfile(
                metrics=["gdp_per_capita", "rule_of_law"],
                normalization_overrides={
                    "gdp_per_capita": NormalizationMethod.MINMAX,
                },
            )
        },
    )

    result = normalize_dataframe(
        df,
        metrics_config=metrics_config,
        scoring_config=scoring_config,
        profile_name="default",
        method="rank",
    )

    assert set(result[NORMALIZATION_METHOD_COLUMN].unique().tolist()) == {"rank"}


def test_metric_specific_overrides_take_highest_precedence():
    df = (
        build_example_metric_dataframe()
        .loc[lambda frame: frame["metric_id"].isin(["gdp_per_capita", "rule_of_law"])]
        .copy()
    )

    result = normalize_dataframe(
        df,
        method="minmax",
        method_overrides={"rule_of_law": "percentile"},
    )

    methods = result.groupby("metric_id")[NORMALIZATION_METHOD_COLUMN].first().to_dict()
    assert methods == {
        "gdp_per_capita": "minmax",
        "rule_of_law": "percentile",
    }


def test_log_minmax_raises_on_zero_or_negative_values():
    df = (
        build_example_metric_dataframe()
        .loc[
            lambda frame: (frame["metric_id"] == "gdp_per_capita")
            & (frame["year"] == 2022)
        ]
        .copy()
    )
    df.loc[df.index[0], "value"] = 0.0

    with pytest.raises(ValueError, match="strictly positive"):
        normalize_metric(df, method="log-minmax")
