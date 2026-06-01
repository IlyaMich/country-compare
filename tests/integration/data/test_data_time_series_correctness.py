from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from country_compare.data.trend_quality import load_trend_rules, scan_trend_anomalies

pytestmark = pytest.mark.integration

TREND_RULES_PATH = (
    Path(__file__).resolve().parents[2]
    / "fixtures"
    / "data"
    / "trend_review_rules.yaml"
)

MAX_ABSOLUTE_STEP_BY_METRIC = {
    "life_expectancy": 5.0,
    "life_expectancy_female": 5.0,
    "life_expectancy_male": 5.0,
    "rule_of_law": 0.5,
    "democracy_index": 2.0,
    "internet_users_pct": 35.0,
    "unemployment_pct": 35.0,
    "labor_participation_pct": 25.0,
    "youth_literacy_pct": 25.0,
    "education_spending_pct_gdp": 25.0,
    "rnd_expenditure_pct_gdp": 10.0,
    "military_exp_pct_gdp": 100.0,
    "market_cap_pct_gdp": 1000.0,
    "inflation": 100.0,
    "consumer_price_index": 500.0,
    "crude_death_rate": 25.0,
    "population_growth_pct": 15.0,
    "top10_income_share": 25.0,
}

# Relative checks are only meaningful for comparatively stable scales.
# They are intentionally not applied to USD, LCU, count, generic percent,
# growth rates, or CPI because those can legitimately move sharply.
MAX_RELATIVE_STEP_BY_UNIT = {
    "years": 0.35,
    "index": 5.0,
    "score_0_10": 1.0,
    "per_1000_people": 5.0,
}


def _sample(
    records: list[dict[str, object]], limit: int = 25
) -> list[dict[str, object]]:
    return records[:limit]


def test_no_duplicate_time_series_years_per_country_metric(
    data_correctness_context,
) -> None:
    dataframe = data_correctness_context.dataframe

    duplicated = dataframe.duplicated(
        subset=["country_code", "metric_id", "year"],
        keep=False,
    )

    assert not duplicated.any(), (
        dataframe.loc[
            duplicated,
            ["country_code", "metric_id", "year"],
        ]
        .head(25)
        .to_dict("records")
    )


def test_no_unreviewed_metric_aware_time_series_anomalies(
    data_correctness_context,
) -> None:
    rules = load_trend_rules(TREND_RULES_PATH)
    result = scan_trend_anomalies(data_correctness_context.dataframe, rules)

    assert result["missing_columns"] == []
    assert result["unreviewed_anomaly_count"] == 0, result[
        "sample_unreviewed_anomalies"
    ]


def test_time_series_year_and_value_columns_are_numeric(
    data_correctness_context,
) -> None:
    dataframe = data_correctness_context.dataframe.copy()

    years = pd.to_numeric(dataframe["year"], errors="coerce")
    values = pd.to_numeric(dataframe["value"], errors="coerce")

    assert years.notna().all()
    assert values.notna().all()
