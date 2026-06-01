from __future__ import annotations

import pandas as pd
import pytest

from tests.integration.data.fixture_rules import load_yaml_fixture

pytestmark = pytest.mark.integration


def test_known_metrics_use_expected_units_and_categories(
    data_correctness_context,
) -> None:
    fixture = load_yaml_fixture("metric_unit_rules.yaml")
    dataframe = data_correctness_context.dataframe

    metric_rules = fixture.get("metrics", {})
    if not isinstance(metric_rules, dict):
        raise AssertionError("metric_unit_rules.yaml metrics must be a mapping.")

    mismatches: list[dict[str, object]] = []

    for metric_id, rules in metric_rules.items():
        if not isinstance(rules, dict):
            raise AssertionError(f"Rules for metric {metric_id!r} must be a mapping.")

        metric_rows = dataframe[dataframe["metric_id"] == str(metric_id)]
        if metric_rows.empty:
            continue

        expected_unit = rules.get("unit")
        expected_category = rules.get("category")

        actual_units = sorted(
            metric_rows["unit"].dropna().astype(str).unique().tolist()
        )
        actual_categories = sorted(
            metric_rows["category"].dropna().astype(str).unique().tolist()
        )

        if expected_unit is not None and actual_units != [str(expected_unit)]:
            mismatches.append(
                {
                    "metric_id": metric_id,
                    "field": "unit",
                    "expected": expected_unit,
                    "actual": actual_units,
                }
            )

        if expected_category is not None and actual_categories != [
            str(expected_category)
        ]:
            mismatches.append(
                {
                    "metric_id": metric_id,
                    "field": "category",
                    "expected": expected_category,
                    "actual": actual_categories,
                }
            )

    assert mismatches == []


def test_units_are_consistent_per_metric(data_correctness_context) -> None:
    dataframe = data_correctness_context.dataframe

    inconsistent: list[dict[str, object]] = []

    for metric_id, group in dataframe.groupby("metric_id", dropna=False):
        units = sorted(group["unit"].dropna().astype(str).unique().tolist())
        if len(units) != 1:
            inconsistent.append({"metric_id": metric_id, "units": units})

    assert inconsistent == []


def test_values_are_plausible_for_declared_unit_scale(data_correctness_context) -> None:
    fixture = load_yaml_fixture("metric_unit_rules.yaml")
    unit_rules = fixture.get("unit_scale_rules", {})

    if not isinstance(unit_rules, dict):
        raise AssertionError(
            "metric_unit_rules.yaml unit_scale_rules must be a mapping."
        )

    dataframe = data_correctness_context.dataframe.copy()
    dataframe["value"] = pd.to_numeric(dataframe["value"], errors="coerce")

    violations: list[dict[str, object]] = []

    for unit, rules in unit_rules.items():
        if not isinstance(rules, dict):
            raise AssertionError(f"Rules for unit {unit!r} must be a mapping.")

        unit_rows = dataframe[dataframe["unit"].astype(str) == str(unit)]
        if unit_rows.empty:
            continue

        min_value = rules.get("min_value")
        max_value = rules.get("max_value")

        if min_value is not None:
            below = unit_rows[unit_rows["value"] < float(min_value)]
            violations.extend(
                {
                    "unit": unit,
                    "rule": f"value >= {min_value}",
                    "country_code": row.country_code,
                    "metric_id": row.metric_id,
                    "year": int(row.year),
                    "value": float(row.value),
                }
                for row in below.itertuples(index=False)
            )

        if max_value is not None:
            above = unit_rows[unit_rows["value"] > float(max_value)]
            violations.extend(
                {
                    "unit": unit,
                    "rule": f"value <= {max_value}",
                    "country_code": row.country_code,
                    "metric_id": row.metric_id,
                    "year": int(row.year),
                    "value": float(row.value),
                }
                for row in above.itertuples(index=False)
            )

    assert violations == []
