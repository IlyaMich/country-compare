from __future__ import annotations

import pandas as pd
import pytest

from tests.integration.data.fixture_rules import load_yaml_fixture

pytestmark = pytest.mark.integration


def test_metric_values_fall_within_plausibility_ranges(
    data_correctness_context,
) -> None:
    fixture = load_yaml_fixture("metric_plausibility_rules.yaml")
    metric_rules = fixture.get("metrics", {})

    if not isinstance(metric_rules, dict):
        raise AssertionError(
            "metric_plausibility_rules.yaml metrics must be a mapping."
        )

    dataframe = data_correctness_context.dataframe.copy()
    dataframe["value"] = pd.to_numeric(dataframe["value"], errors="coerce")

    violations: list[dict[str, object]] = []

    for metric_id, rules in metric_rules.items():
        if not isinstance(rules, dict):
            raise AssertionError(f"Rules for metric {metric_id!r} must be a mapping.")

        rows = dataframe[dataframe["metric_id"] == str(metric_id)]
        if rows.empty:
            continue

        min_value = rules.get("min_value")
        max_value = rules.get("max_value")
        severity = rules.get("severity", "hard_fail")

        if min_value is not None:
            below = rows[rows["value"] < float(min_value)]
            violations.extend(
                {
                    "metric_id": metric_id,
                    "country_code": row.country_code,
                    "year": int(row.year),
                    "value": float(row.value),
                    "expected": f">= {min_value}",
                    "severity": severity,
                }
                for row in below.itertuples(index=False)
            )

        if max_value is not None:
            above = rows[rows["value"] > float(max_value)]
            violations.extend(
                {
                    "metric_id": metric_id,
                    "country_code": row.country_code,
                    "year": int(row.year),
                    "value": float(row.value),
                    "expected": f"<= {max_value}",
                    "severity": severity,
                }
                for row in above.itertuples(index=False)
            )

    hard_failures = [
        violation
        for violation in violations
        if violation.get("severity") == "hard_fail"
    ]

    assert hard_failures == []


def test_unit_hard_bounds_are_respected(data_correctness_context) -> None:
    fixture = load_yaml_fixture("metric_plausibility_rules.yaml")
    unit_rules = fixture.get("unit_hard_bounds", {})

    if not isinstance(unit_rules, dict):
        raise AssertionError(
            "metric_plausibility_rules.yaml unit_hard_bounds must be a mapping."
        )

    dataframe = data_correctness_context.dataframe.copy()
    dataframe["value"] = pd.to_numeric(dataframe["value"], errors="coerce")

    violations: list[dict[str, object]] = []

    for unit, rules in unit_rules.items():
        if not isinstance(rules, dict):
            raise AssertionError(f"Rules for unit {unit!r} must be a mapping.")

        rows = dataframe[dataframe["unit"].astype(str) == str(unit)]
        if rows.empty:
            continue

        min_value = rules.get("min_value")
        max_value = rules.get("max_value")

        if min_value is not None:
            below = rows[rows["value"] < float(min_value)]
            violations.extend(
                {
                    "unit": unit,
                    "country_code": row.country_code,
                    "metric_id": row.metric_id,
                    "year": int(row.year),
                    "value": float(row.value),
                    "expected": f">= {min_value}",
                }
                for row in below.itertuples(index=False)
            )

        if max_value is not None:
            above = rows[rows["value"] > float(max_value)]
            violations.extend(
                {
                    "unit": unit,
                    "country_code": row.country_code,
                    "metric_id": row.metric_id,
                    "year": int(row.year),
                    "value": float(row.value),
                    "expected": f"<= {max_value}",
                }
                for row in above.itertuples(index=False)
            )

    assert violations == []
