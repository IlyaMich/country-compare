
import pandas as pd
import pytest

from country_compare.config.models import YearStrategy
from country_compare.data.examples import build_example_metric_dataframe
from country_compare.metrics.filtering import (
    apply_year_strategy,
    filter_countries,
    filter_dataset,
    filter_metrics,
    select_common_year,
    select_latest_per_metric,
    select_target_year,
)


def test_filter_countries_include():
    df = build_example_metric_dataframe()

    result = filter_countries(df, include=["ISR", "SGP"])

    assert set(result["country_code"].unique()) == {"ISR", "SGP"}
    # 2 countries × 5 metrics × 2 years = 20
    assert len(result) == 20


def test_filter_countries_exclude():
    df = build_example_metric_dataframe()

    result = filter_countries(df, exclude=["DEU"])

    # Excluding DEU, remaining: ISR, SGP, CAN, JPN
    assert set(result["country_code"].unique()) == {"ISR", "SGP", "CAN", "JPN"}
    # 4 countries × 5 metrics × 2 years = 40
    assert len(result) == 40


def test_filter_metrics_include():
    df = build_example_metric_dataframe()

    result = filter_metrics(df, include=["gdp_per_capita", "rule_of_law"])

    assert set(result["metric_id"].unique()) == {"gdp_per_capita", "rule_of_law"}
    # 2 metrics × 5 countries × 2 years = 20
    assert len(result) == 20


def test_filter_metrics_exclude():
    df = build_example_metric_dataframe()

    result = filter_metrics(df, exclude=["democracy_index"])

    # Excluding democracy_index, remaining: gdp_per_capita, rule_of_law, inflation, life_expectancy
    expected_metrics = {"gdp_per_capita", "rule_of_law", "inflation", "life_expectancy"}
    assert set(result["metric_id"].unique()) == expected_metrics
    # 4 metrics × 5 countries × 2 years = 40
    assert len(result) == 40


def test_latest_per_metric_selects_latest_row_per_country_metric():
    df = build_example_metric_dataframe()

    result = select_latest_per_metric(df)

    # Should select the latest year for each (country, metric) pair
    # 5 countries × 5 metrics = 25
    assert len(result) == 25
    observed = {
        (row.country_code, row.metric_id): int(row.year)
        for row in result.itertuples(index=False)
    }
    # All should be 2023 for all (country, metric) pairs
    for (country, metric), year in observed.items():
        assert year == 2023


def test_target_year_filters_single_year():
    df = build_example_metric_dataframe()

    result = select_target_year(df, target_year=2023)

    # All rows for 2023: 5 countries × 5 metrics = 25
    assert len(result) == 25
    assert set(result["year"].astype(int).unique()) == {2023}


def test_target_year_requires_explicit_year():
    df = build_example_metric_dataframe()

    with pytest.raises(ValueError, match="target_year must be provided"):
        select_target_year(df, target_year=None)


def test_common_year_selects_latest_fully_covered_year():
    df = build_example_metric_dataframe()

    result = select_common_year(df)

    # All metrics and countries have both 2022 and 2023, so latest is 2023
    # 5 countries × 5 metrics = 25
    assert len(result) == 25
    assert set(result["year"].astype(int).unique()) == {2023}


def test_common_year_raises_when_no_fully_covered_year_exists():
    df = build_example_metric_dataframe()

    # Remove one country/metric pair for each metric across all years
    mask = ~(
        ((df["metric_id"] == "gdp_per_capita") & (df["country_code"] == "ISR")) |
        ((df["metric_id"] == "rule_of_law") & (df["country_code"] == "DEU")) |
        ((df["metric_id"] == "democracy_index") & (df["country_code"] == "SGP")) |
        ((df["metric_id"] == "inflation") & (df["country_code"] == "CAN")) |
        ((df["metric_id"] == "life_expectancy") & (df["country_code"] == "JPN"))
    )
    broken = df.loc[mask].copy()

    with pytest.raises(ValueError, match="no common year provides full coverage"):
        select_common_year(broken)


def test_filtering_preserves_input_immutability():
    df = build_example_metric_dataframe()
    original = df.copy(deep=True)

    _ = filter_dataset(
        df,
        countries_include=["ISR", "DEU"],
        metrics_include=["gdp_per_capita"],
        year_strategy=YearStrategy.LATEST_PER_METRIC,
    )

    pd.testing.assert_frame_equal(df, original)


def test_filtering_preserves_schema_and_dtypes():
    df = build_example_metric_dataframe()

    result = filter_dataset(
        df,
        countries_include=["ISR", "DEU"],
        metrics_include=["gdp_per_capita", "rule_of_law"],
        year_strategy=YearStrategy.COMMON_YEAR,
    )

    assert list(result.columns) == list(df.columns)
    pd.testing.assert_series_equal(result.dtypes, df.dtypes)


def test_empty_result_is_supported():
    df = build_example_metric_dataframe()

    result = filter_dataset(
        df,
        countries_include=["USA"],
        metrics_include=["nonexistent_metric"],
    )

    assert result.empty
    assert list(result.columns) == list(df.columns)
    pd.testing.assert_series_equal(result.dtypes, df.dtypes)


def test_apply_year_strategy_accepts_enum_and_string():
    df = build_example_metric_dataframe()

    enum_result = apply_year_strategy(df, YearStrategy.LATEST_PER_METRIC)
    string_result = apply_year_strategy(df, "latest_per_metric")

    pd.testing.assert_frame_equal(
        enum_result.reset_index(drop=True),
        string_result.reset_index(drop=True),
    )
