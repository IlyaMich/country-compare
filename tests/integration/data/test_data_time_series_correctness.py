from __future__ import annotations

import warnings

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


def test_extreme_year_over_year_absolute_jumps_are_reviewed(
    data_correctness_context,
) -> None:
    dataframe = data_correctness_context.dataframe.copy()
    dataframe["year"] = pd.to_numeric(dataframe["year"], errors="coerce")
    dataframe["value"] = pd.to_numeric(dataframe["value"], errors="coerce")
    dataframe = dataframe.dropna(subset=["country_code", "metric_id", "year", "value"])

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

            previous_year = int(previous.year)
            current_year = int(row.year)

            # Only compare consecutive observations. Gaps are coverage issues,
            # not necessarily value-correctness issues.
            if current_year - previous_year != 1:
                previous = row
                continue

            change = abs(float(row.value) - float(previous.value))
            if change > threshold:
                violations.append(
                    {
                        "country_code": country_code,
                        "metric_id": metric_id,
                        "previous_year": previous_year,
                        "current_year": current_year,
                        "previous_value": float(previous.value),
                        "current_value": float(row.value),
                        "absolute_change": change,
                        "threshold": threshold,
                    }
                )

            previous = row

    if violations:
        warnings.warn(
            "Found year-over-year absolute jumps that should be reviewed "
            f"manually before release. Count={len(violations)}. "
            f"Sample={_sample(violations)}",
            UserWarning,
            stacklevel=2,
        )


def test_extreme_year_over_year_relative_scale_shifts_are_reviewed(
    data_correctness_context,
) -> None:
    dataframe = data_correctness_context.dataframe.copy()
    dataframe["year"] = pd.to_numeric(dataframe["year"], errors="coerce")
    dataframe["value"] = pd.to_numeric(dataframe["value"], errors="coerce")
    dataframe = dataframe.dropna(subset=["country_code", "metric_id", "year", "value"])

    violations: list[dict[str, object]] = []

    for (country_code, metric_id), group in dataframe.groupby(
        ["country_code", "metric_id"]
    ):
        group = group.sort_values("year")
        unit_values = group["unit"].dropna().astype(str).unique().tolist()
        if not unit_values:
            continue

        unit = unit_values[0]
        threshold = MAX_RELATIVE_STEP_BY_UNIT.get(unit)
        if threshold is None:
            continue

        previous = None

        for row in group.itertuples(index=False):
            if previous is None:
                previous = row
                continue

            previous_year = int(previous.year)
            current_year = int(row.year)

            if current_year - previous_year != 1:
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
                        "previous_year": previous_year,
                        "current_year": current_year,
                        "previous_value": previous_value,
                        "current_value": current_value,
                        "relative_change": relative_change,
                        "threshold": threshold,
                    }
                )

            previous = row

    if violations:
        warnings.warn(
            "Found year-over-year relative shifts that should be reviewed "
            f"manually before release. Count={len(violations)}. "
            f"Sample={_sample(violations)}",
            UserWarning,
            stacklevel=2,
        )
