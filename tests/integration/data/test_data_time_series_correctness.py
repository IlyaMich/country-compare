from __future__ import annotations

import pandas as pd
import pytest

pytestmark = pytest.mark.integration

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
    "military_exp_pct_gdp": 25.0,
    "market_cap_pct_gdp": 500.0,
    "inflation": 25.0,
    "consumer_price_index": 150.0,
    "crude_death_rate": 25.0,
    "population_growth_pct": 15.0,
    "top10_income_share": 25.0,
}

MAX_RELATIVE_STEP_BY_UNIT = {
    "USD": 5.0,
    "LCU": 10.0,
    "count": 10.0,
    "percent": 10.0,
    "years": 0.25,
    "index": 2.0,
    "score_0_10": 0.5,
    "index_2010_100": 2.0,
    "per_1000_people": 2.0,
}


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


def test_no_extreme_year_over_year_absolute_jumps(data_correctness_context) -> None:
    dataframe = data_correctness_context.dataframe.copy()
    dataframe["year"] = pd.to_numeric(dataframe["year"], errors="coerce")
    dataframe["value"] = pd.to_numeric(dataframe["value"], errors="coerce")

    violations: list[dict[str, object]] = []

    for (country_code, metric_id), group in dataframe.groupby(
        ["country_code", "metric_id"]
    ):
        threshold = MAX_ABSOLUTE_STEP_BY_METRIC.get(str(metric_id))
        if threshold is None:
            continue

        group = group.sort_values("year")
        previous = None

        for row in group.itertuples(index=False):
            if previous is None:
                previous = row
                continue

            change = abs(float(row.value) - float(previous.value))
            if change > threshold:
                violations.append(
                    {
                        "country_code": country_code,
                        "metric_id": metric_id,
                        "previous_year": int(previous.year),
                        "current_year": int(row.year),
                        "previous_value": float(previous.value),
                        "current_value": float(row.value),
                        "absolute_change": change,
                        "threshold": threshold,
                    }
                )

            previous = row

    assert violations == []


def test_no_extreme_year_over_year_relative_scale_shifts(
    data_correctness_context,
) -> None:
    dataframe = data_correctness_context.dataframe.copy()
    dataframe["year"] = pd.to_numeric(dataframe["year"], errors="coerce")
    dataframe["value"] = pd.to_numeric(dataframe["value"], errors="coerce")

    violations: list[dict[str, object]] = []

    for (country_code, metric_id), group in dataframe.groupby(
        ["country_code", "metric_id"]
    ):
        group = group.sort_values("year")
        unit = str(group["unit"].dropna().iloc[0])
        threshold = MAX_RELATIVE_STEP_BY_UNIT.get(unit, 10.0)
        previous = None

        for row in group.itertuples(index=False):
            if previous is None:
                previous = row
                continue

            previous_value = float(previous.value)
            current_value = float(row.value)

            if abs(previous_value) < 1.0:
                previous = row
                continue

            relative_change = abs(current_value - previous_value) / abs(previous_value)
            if relative_change > threshold:
                violations.append(
                    {
                        "country_code": country_code,
                        "metric_id": metric_id,
                        "unit": unit,
                        "previous_year": int(previous.year),
                        "current_year": int(row.year),
                        "previous_value": previous_value,
                        "current_value": current_value,
                        "relative_change": relative_change,
                        "threshold": threshold,
                    }
                )

            previous = row

    assert violations == []
