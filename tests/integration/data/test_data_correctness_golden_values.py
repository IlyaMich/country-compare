from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml

pytestmark = pytest.mark.integration

GOLDEN_VALUES_PATH = Path("tests/fixtures/data/golden_values.yaml")

DEFAULT_EXAMPLE_GOLDEN_VALUES: list[dict[str, Any]] = [
    {
        "country_code": "ISR",
        "metric_id": "gdp_per_capita",
        "year": 2025,
        "expected_value": 59000.0,
        "tolerance_abs": 0.001,
        "unit": "USD",
    },
    {
        "country_code": "CAN",
        "metric_id": "life_expectancy",
        "year": 2025,
        "expected_value": 82.7,
        "tolerance_abs": 0.001,
        "unit": "years",
    },
    {
        "country_code": "DEU",
        "metric_id": "rule_of_law",
        "year": 2025,
        "expected_value": 0.86,
        "tolerance_abs": 0.001,
        "unit": "index",
    },
    {
        "country_code": "SGP",
        "metric_id": "democracy_index",
        "year": 2025,
        "expected_value": 6.4,
        "tolerance_abs": 0.001,
        "unit": "score_0_10",
    },
    {
        "country_code": "JPN",
        "metric_id": "inflation",
        "year": 2025,
        "expected_value": 1.8,
        "tolerance_abs": 0.001,
        "unit": "percent",
    },
]


def _load_golden_values(is_example_dataset: bool) -> list[dict[str, Any]]:
    if GOLDEN_VALUES_PATH.exists():
        with GOLDEN_VALUES_PATH.open("r", encoding="utf-8") as file:
            loaded = yaml.safe_load(file) or []

        if not isinstance(loaded, list):
            raise AssertionError(f"{GOLDEN_VALUES_PATH} must contain a YAML list.")

        return loaded

    if is_example_dataset:
        return DEFAULT_EXAMPLE_GOLDEN_VALUES

    pytest.skip(
        f"No {GOLDEN_VALUES_PATH} file found. Add release-specific golden values "
        "before running golden-value checks against a real release dataset."
    )


def test_golden_values_match_expected_reference_rows(data_correctness_context) -> None:
    dataframe = data_correctness_context.dataframe
    golden_values = _load_golden_values(data_correctness_context.is_example_dataset)

    failures: list[str] = []

    for expected in golden_values:
        country_code = expected["country_code"]
        metric_id = expected["metric_id"]
        year = expected["year"]

        matching_rows = dataframe[
            (dataframe["country_code"] == country_code)
            & (dataframe["metric_id"] == metric_id)
            & (dataframe["year"].astype(int) == int(year))
        ]

        if len(matching_rows) != 1:
            failures.append(
                f"Expected exactly one row for {country_code}/{metric_id}/{year}, "
                f"found {len(matching_rows)}."
            )
            continue

        row = matching_rows.iloc[0]
        actual_value = float(row["value"])
        expected_value = float(expected["expected_value"])
        tolerance_abs = float(expected.get("tolerance_abs", 0.0))
        tolerance_pct = expected.get("tolerance_pct")

        allowed_delta = tolerance_abs
        if tolerance_pct is not None:
            allowed_delta = max(
                allowed_delta,
                abs(expected_value) * float(tolerance_pct) / 100.0,
            )

        if abs(actual_value - expected_value) > allowed_delta:
            failures.append(
                f"{country_code}/{metric_id}/{year}: expected {expected_value} "
                f"± {allowed_delta}, got {actual_value}."
            )

        expected_unit = expected.get("unit")
        if expected_unit is not None and str(row["unit"]) != str(expected_unit):
            failures.append(
                f"{country_code}/{metric_id}/{year}: expected unit "
                f"{expected_unit!r}, got {row['unit']!r}."
            )

    assert failures == []
