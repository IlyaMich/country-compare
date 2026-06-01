from __future__ import annotations

import pytest

from tests.integration.data.fixture_rules import (
    as_list,
    load_yaml_fixture,
    normalize_text,
)

pytestmark = pytest.mark.integration


def _combined_source_rules(
    fixture: dict[str, object],
    metric_id: str,
) -> dict[str, object]:
    defaults = fixture.get("defaults", {})
    metrics = fixture.get("metrics", {})

    if not isinstance(defaults, dict):
        raise AssertionError("expected_metric_sources.yaml defaults must be a mapping.")

    if not isinstance(metrics, dict):
        raise AssertionError("expected_metric_sources.yaml metrics must be a mapping.")

    metric_rules = metrics.get(metric_id, {})
    if metric_rules is None:
        metric_rules = {}

    if not isinstance(metric_rules, dict):
        raise AssertionError(f"Rules for metric {metric_id!r} must be a mapping.")

    combined = dict(defaults)
    combined.update(metric_rules)

    # For contains-style checks, combine defaults and metric-specific values
    # instead of replacing defaults. This keeps the synthetic example dataset
    # valid while still allowing stricter source-family rules for release data.
    for key in ("source_name_contains", "source_url_contains"):
        combined[key] = as_list(defaults.get(key)) + as_list(metric_rules.get(key))

    return combined


def test_every_metric_has_non_empty_source_metadata(data_correctness_context) -> None:
    dataframe = data_correctness_context.dataframe

    missing_source_rows = dataframe[
        dataframe["source_name"].isna()
        | (dataframe["source_name"].astype(str).str.strip() == "")
        | dataframe["source_url"].isna()
        | (dataframe["source_url"].astype(str).str.strip() == "")
    ]

    assert missing_source_rows.empty, (
        missing_source_rows[
            ["country_code", "metric_id", "year", "source_name", "source_url"]
        ]
        .head(25)
        .to_dict("records")
    )


def test_source_urls_are_http_urls(data_correctness_context) -> None:
    dataframe = data_correctness_context.dataframe

    invalid_urls = dataframe[
        ~dataframe["source_url"].astype(str).str.startswith(("http://", "https://"))
    ]

    assert invalid_urls.empty, (
        invalid_urls[["country_code", "metric_id", "year", "source_url"]]
        .head(25)
        .to_dict("records")
    )


def test_source_metadata_is_consistent_per_metric(data_correctness_context) -> None:
    dataframe = data_correctness_context.dataframe

    inconsistent: list[dict[str, object]] = []

    for metric_id, group in dataframe.groupby("metric_id", dropna=False):
        for column in ("source_name", "source_url"):
            values = sorted(group[column].dropna().astype(str).unique().tolist())
            if len(values) > 1:
                inconsistent.append(
                    {
                        "metric_id": metric_id,
                        "column": column,
                        "distinct_values": values,
                    }
                )

    assert inconsistent == []


def test_metric_sources_match_expected_source_family_fixture(
    data_correctness_context,
) -> None:
    fixture = load_yaml_fixture("expected_metric_sources.yaml")
    dataframe = data_correctness_context.dataframe

    failures: list[dict[str, object]] = []

    for metric_id, group in dataframe.groupby("metric_id"):
        metric_id = str(metric_id)
        rules = _combined_source_rules(fixture, metric_id)

        source_name_contains = [
            normalize_text(value)
            for value in as_list(rules.get("source_name_contains"))
        ]
        source_url_contains = [
            normalize_text(value) for value in as_list(rules.get("source_url_contains"))
        ]
        expected_unit = rules.get("unit")
        expected_category = rules.get("category")

        actual_source_names = sorted(
            group["source_name"].dropna().astype(str).unique().tolist()
        )
        actual_source_urls = sorted(
            group["source_url"].dropna().astype(str).unique().tolist()
        )
        actual_units = sorted(group["unit"].dropna().astype(str).unique().tolist())
        actual_categories = sorted(
            group["category"].dropna().astype(str).unique().tolist()
        )

        normalized_source_names = [
            normalize_text(value) for value in actual_source_names
        ]
        normalized_source_urls = [normalize_text(value) for value in actual_source_urls]

        if source_name_contains and not any(
            expected in actual
            for expected in source_name_contains
            for actual in normalized_source_names
        ):
            failures.append(
                {
                    "metric_id": metric_id,
                    "field": "source_name",
                    "expected_contains_any": source_name_contains,
                    "actual": actual_source_names,
                }
            )

        if source_url_contains and not any(
            expected in actual
            for expected in source_url_contains
            for actual in normalized_source_urls
        ):
            failures.append(
                {
                    "metric_id": metric_id,
                    "field": "source_url",
                    "expected_contains_any": source_url_contains,
                    "actual": actual_source_urls,
                }
            )

        if expected_unit is not None and actual_units != [str(expected_unit)]:
            failures.append(
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
            failures.append(
                {
                    "metric_id": metric_id,
                    "field": "category",
                    "expected": expected_category,
                    "actual": actual_categories,
                }
            )

    assert failures == []
