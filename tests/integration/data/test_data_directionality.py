from __future__ import annotations

import pytest

from tests.integration.data.fixture_rules import load_yaml_fixture

pytestmark = pytest.mark.integration


def _expected_directionality() -> dict[str, bool]:
    fixture = load_yaml_fixture("expected_directionality.yaml")
    metric_rules = fixture.get("metrics", {})

    if not isinstance(metric_rules, dict):
        raise AssertionError("expected_directionality.yaml metrics must be a mapping.")

    return {
        str(metric_id): bool(expected) for metric_id, expected in metric_rules.items()
    }


def test_higher_is_better_is_consistent_per_metric(data_correctness_context) -> None:
    dataframe = data_correctness_context.dataframe

    inconsistent: list[dict[str, object]] = []

    for metric_id, group in dataframe.groupby("metric_id", dropna=False):
        values = sorted(
            group["higher_is_better"].dropna().astype(bool).unique().tolist()
        )
        if len(values) != 1:
            inconsistent.append(
                {"metric_id": metric_id, "higher_is_better_values": values}
            )

    assert inconsistent == []


def test_known_metric_directionality_matches_expectations(
    data_correctness_context,
) -> None:
    dataframe = data_correctness_context.dataframe
    expected_directionality = _expected_directionality()

    mismatches: list[dict[str, object]] = []

    for metric_id, expected_value in expected_directionality.items():
        rows = dataframe[dataframe["metric_id"].astype(str) == metric_id]
        if rows.empty:
            continue

        actual_values = sorted(
            rows["higher_is_better"].dropna().astype(bool).unique().tolist()
        )
        if actual_values != [expected_value]:
            mismatches.append(
                {
                    "metric_id": metric_id,
                    "expected": expected_value,
                    "actual_values": actual_values,
                }
            )

    assert mismatches == []


def test_latest_year_best_country_respects_directionality(
    data_correctness_context,
) -> None:
    dataframe = data_correctness_context.dataframe.copy()

    failures: list[dict[str, object]] = []

    for metric_id, group in dataframe.groupby("metric_id"):
        latest_year = int(group["year"].max())
        latest_rows = group[group["year"].astype(int) == latest_year]

        if latest_rows.empty:
            continue

        higher_is_better = bool(latest_rows["higher_is_better"].iloc[0])
        values = latest_rows["value"].astype(float)

        expected_best_value = float(values.max() if higher_is_better else values.min())
        selected_best_value = float(
            latest_rows.sort_values(
                by="value",
                ascending=not higher_is_better,
            ).iloc[
                0
            ]["value"]
        )

        if selected_best_value != expected_best_value:
            failures.append(
                {
                    "metric_id": metric_id,
                    "latest_year": latest_year,
                    "higher_is_better": higher_is_better,
                    "expected_best_value": expected_best_value,
                    "selected_best_value": selected_best_value,
                }
            )

    assert failures == []
