from __future__ import annotations

import math
from typing import Any

import pandas as pd
import pytest

from tests.integration.data.fixture_rules import (
    as_list,
    load_yaml_fixture,
    normalize_text,
)

pytestmark = pytest.mark.integration


def _golden_values_for_active_dataset(data_correctness_context) -> list[dict[str, Any]]:
    fixture = load_yaml_fixture("golden_values.yaml")

    section_name = (
        "example_dataset"
        if data_correctness_context.is_example_dataset
        else "release_dataset"
    )

    section = fixture.get(section_name, {})
    if not isinstance(section, dict):
        raise AssertionError(f"golden_values.yaml {section_name} must be a mapping.")

    golden_values = section.get("golden_values", [])
    if not isinstance(golden_values, list):
        raise AssertionError(
            f"golden_values.yaml {section_name}.golden_values must be a list."
        )

    if not golden_values:
        pytest.skip(
            f"No golden values configured for {section_name}. "
            "Add release golden values before using this as a release gate."
        )

    for index, golden_value in enumerate(golden_values):
        if not isinstance(golden_value, dict):
            raise AssertionError(
                f"golden_values.yaml {section_name}.golden_values[{index}] "
                "must be a mapping."
            )

    return golden_values


def _allowed_delta(expected_value: float, golden_value: dict[str, Any]) -> float:
    tolerance_abs = golden_value.get("tolerance_abs", 0.0)
    tolerance_pct = golden_value.get("tolerance_pct", 0.0)

    allowed_delta = float(tolerance_abs or 0.0)

    if tolerance_pct is not None:
        allowed_delta = max(
            allowed_delta,
            abs(expected_value) * float(tolerance_pct or 0.0) / 100.0,
        )

    return allowed_delta


def _contains_any(actual_values: list[str], expected_fragments: list[str]) -> bool:
    normalized_actual_values = [normalize_text(value) for value in actual_values]
    normalized_expected_fragments = [
        normalize_text(value) for value in expected_fragments
    ]

    return any(
        expected_fragment in actual_value
        for expected_fragment in normalized_expected_fragments
        for actual_value in normalized_actual_values
    )


def test_golden_values_match_expected_reference_rows(data_correctness_context) -> None:
    dataframe = data_correctness_context.dataframe.copy()
    golden_values = _golden_values_for_active_dataset(data_correctness_context)

    dataframe["year"] = pd.to_numeric(dataframe["year"], errors="coerce").astype(
        "Int64"
    )
    dataframe["value"] = pd.to_numeric(dataframe["value"], errors="coerce")

    failures: list[dict[str, object]] = []

    for golden_value in golden_values:
        country_code = str(golden_value["country_code"])
        metric_id = str(golden_value["metric_id"])
        year = int(golden_value["year"])

        matching_rows = dataframe[
            (dataframe["country_code"].astype(str) == country_code)
            & (dataframe["metric_id"].astype(str) == metric_id)
            & (dataframe["year"].astype("Int64") == year)
        ]

        if len(matching_rows) != 1:
            failures.append(
                {
                    "country_code": country_code,
                    "metric_id": metric_id,
                    "year": year,
                    "reason": "row_count_mismatch",
                    "expected_row_count": 1,
                    "actual_row_count": len(matching_rows),
                }
            )
            continue

        row = matching_rows.iloc[0]

        expected_value = float(golden_value["expected_value"])
        actual_value = float(row["value"])
        allowed_delta = _allowed_delta(expected_value, golden_value)
        actual_delta = abs(actual_value - expected_value)

        if not math.isfinite(actual_value) or actual_delta > allowed_delta:
            failures.append(
                {
                    "country_code": country_code,
                    "metric_id": metric_id,
                    "year": year,
                    "reason": "value_mismatch",
                    "expected_value": expected_value,
                    "actual_value": actual_value,
                    "allowed_delta": allowed_delta,
                    "actual_delta": actual_delta,
                }
            )

        expected_unit = golden_value.get("unit")
        if expected_unit is not None and str(row["unit"]) != str(expected_unit):
            failures.append(
                {
                    "country_code": country_code,
                    "metric_id": metric_id,
                    "year": year,
                    "reason": "unit_mismatch",
                    "expected": expected_unit,
                    "actual": row["unit"],
                }
            )

        expected_category = golden_value.get("category")
        if expected_category is not None and str(row["category"]) != str(
            expected_category
        ):
            failures.append(
                {
                    "country_code": country_code,
                    "metric_id": metric_id,
                    "year": year,
                    "reason": "category_mismatch",
                    "expected": expected_category,
                    "actual": row["category"],
                }
            )

        if "higher_is_better" in golden_value:
            expected_direction = bool(golden_value["higher_is_better"])
            actual_direction = bool(row["higher_is_better"])

            if actual_direction != expected_direction:
                failures.append(
                    {
                        "country_code": country_code,
                        "metric_id": metric_id,
                        "year": year,
                        "reason": "directionality_mismatch",
                        "expected": expected_direction,
                        "actual": actual_direction,
                    }
                )

        source_name_contains = as_list(golden_value.get("source_name_contains"))
        if source_name_contains and not _contains_any(
            [str(row["source_name"])],
            source_name_contains,
        ):
            failures.append(
                {
                    "country_code": country_code,
                    "metric_id": metric_id,
                    "year": year,
                    "reason": "source_name_mismatch",
                    "expected_contains_any": source_name_contains,
                    "actual": row["source_name"],
                }
            )

        source_url_contains = as_list(golden_value.get("source_url_contains"))
        if source_url_contains and not _contains_any(
            [str(row["source_url"])],
            source_url_contains,
        ):
            failures.append(
                {
                    "country_code": country_code,
                    "metric_id": metric_id,
                    "year": year,
                    "reason": "source_url_mismatch",
                    "expected_contains_any": source_url_contains,
                    "actual": row["source_url"],
                }
            )

    assert failures == []
