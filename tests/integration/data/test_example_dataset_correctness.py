from __future__ import annotations

from typing import Any

import pytest

from country_compare.data.contract import PRIMARY_KEY_COLUMNS, REQUIRED_COLUMNS
from country_compare.data.examples import (
    COUNTRIES,
    METRICS,
    build_example_metric_dataframe,
)
from country_compare.data.validation import validate_dataframe

pytestmark = pytest.mark.integration


def test_example_metric_dataframe_matches_source_definitions() -> None:
    dataframe = build_example_metric_dataframe()

    assert not dataframe.empty
    assert set(REQUIRED_COLUMNS).issubset(dataframe.columns)
    assert set(dataframe["country_code"].unique()) == set(COUNTRIES)
    assert set(dataframe["metric_id"].unique()) == set(METRICS)

    for metric_id, metric_metadata in METRICS.items():
        yearly_values = metric_metadata["yearly_values"]
        assert isinstance(yearly_values, dict)

        expected_row_count = sum(
            len(values_by_country) for values_by_country in yearly_values.values()
        )
        metric_rows = dataframe[dataframe["metric_id"] == metric_id]

        assert len(metric_rows) == expected_row_count
        assert set(metric_rows["year"].astype(int).unique()) == set(yearly_values)
        assert set(metric_rows["country_code"].unique()).issubset(set(COUNTRIES))


def test_example_metric_dataframe_passes_canonical_validation() -> None:
    dataframe = build_example_metric_dataframe()

    result = validate_dataframe(dataframe)

    assert result.valid, [issue.message for issue in result.issues]


def test_example_metric_dataframe_has_unique_primary_keys() -> None:
    dataframe = build_example_metric_dataframe()

    duplicate_mask = dataframe.duplicated(subset=list(PRIMARY_KEY_COLUMNS), keep=False)

    assert not duplicate_mask.any()


def test_example_metric_metadata_is_consistent_per_metric_id() -> None:
    dataframe = build_example_metric_dataframe()

    metadata_columns = [
        "metric_name",
        "unit",
        "higher_is_better",
        "category",
        "source_name",
        "source_url",
    ]

    inconsistent: list[dict[str, Any]] = []

    for metric_id, group in dataframe.groupby("metric_id", dropna=False):
        for column in metadata_columns:
            distinct_values = group[column].dropna().astype(str).unique().tolist()
            if len(distinct_values) > 1:
                inconsistent.append(
                    {
                        "metric_id": metric_id,
                        "column": column,
                        "distinct_values": distinct_values,
                    }
                )

    assert inconsistent == []


def test_example_metric_dataframe_has_expected_value_quality() -> None:
    dataframe = build_example_metric_dataframe()

    assert dataframe["value"].notna().all()
    assert dataframe["country_code"].str.fullmatch(r"[A-Z]{3}").all()
    assert dataframe["source_url"].str.startswith(("http://", "https://")).all()
