from __future__ import annotations

import pandas as pd
import pytest

from tests.integration.data.fixture_rules import load_yaml_fixture

pytestmark = pytest.mark.integration


def _coverage_section(data_correctness_context) -> dict[str, object]:
    fixture = load_yaml_fixture("release_coverage.yaml")
    section_name = (
        "example_dataset"
        if data_correctness_context.is_example_dataset
        else "release_dataset"
    )

    section = fixture.get(section_name, {})
    if not isinstance(section, dict):
        raise AssertionError(f"release_coverage.yaml {section_name} must be a mapping.")

    return section


def _minimums() -> dict[str, object]:
    fixture = load_yaml_fixture("release_coverage.yaml")
    minimums = fixture.get("default_minimums", {})

    if not isinstance(minimums, dict):
        raise AssertionError(
            "release_coverage.yaml default_minimums must be a mapping."
        )

    return minimums


def test_release_dataset_has_minimum_country_metric_year_coverage(
    data_correctness_context,
) -> None:
    dataframe = data_correctness_context.dataframe
    minimums = _minimums()

    assert dataframe["country_code"].nunique() >= int(minimums["min_country_count"])
    assert dataframe["metric_id"].nunique() >= int(minimums["min_metric_count"])
    assert dataframe["year"].nunique() >= int(minimums["min_year_count"])


def test_release_critical_countries_are_present(data_correctness_context) -> None:
    dataframe = data_correctness_context.dataframe
    section = _coverage_section(data_correctness_context)

    expected_countries = set(str(country) for country in section.get("countries", []))
    actual_countries = set(dataframe["country_code"].dropna().astype(str).unique())

    missing_countries = sorted(expected_countries - actual_countries)

    assert missing_countries == []


def test_release_critical_metrics_are_present(data_correctness_context) -> None:
    dataframe = data_correctness_context.dataframe
    section = _coverage_section(data_correctness_context)

    expected_metrics = set(str(metric) for metric in section.get("metrics", []))
    actual_metrics = set(dataframe["metric_id"].dropna().astype(str).unique())

    missing_metrics = sorted(expected_metrics - actual_metrics)

    assert missing_metrics == []


def test_required_country_metric_pairs_have_enough_observations(
    data_correctness_context,
) -> None:
    dataframe = data_correctness_context.dataframe
    section = _coverage_section(data_correctness_context)

    required_pairs = section.get("required_country_metric_pairs", [])
    if not isinstance(required_pairs, list):
        raise AssertionError(
            "release_coverage.yaml required_country_metric_pairs must be a list."
        )

    failures: list[dict[str, object]] = []

    for pair in required_pairs:
        if not isinstance(pair, dict):
            raise AssertionError("Each required country/metric pair must be a mapping.")

        country_code = str(pair["country_code"])
        metric_id = str(pair["metric_id"])
        min_observations = int(pair.get("min_observations", 1))

        rows = dataframe[
            (dataframe["country_code"].astype(str) == country_code)
            & (dataframe["metric_id"].astype(str) == metric_id)
        ]

        observation_count = int(rows["year"].nunique())

        if observation_count < min_observations:
            failures.append(
                {
                    "country_code": country_code,
                    "metric_id": metric_id,
                    "expected_min_observations": min_observations,
                    "actual_observations": observation_count,
                }
            )

    assert failures == []


def test_prediction_required_metrics_have_enough_history(
    data_correctness_context,
) -> None:
    dataframe = data_correctness_context.dataframe
    section = _coverage_section(data_correctness_context)
    minimums = _minimums()

    prediction_required_metrics = section.get("prediction_required_metrics")
    if not prediction_required_metrics:
        prediction_required_metrics = section.get("metrics", [])

    required_metrics = set(str(metric) for metric in prediction_required_metrics)
    min_observations = int(
        minimums["min_observations_per_country_metric_for_prediction"]
    )

    failures: list[dict[str, object]] = []

    for metric_id in sorted(required_metrics):
        metric_rows = dataframe[dataframe["metric_id"].astype(str) == metric_id]
        if metric_rows.empty:
            continue

        observations_by_country = metric_rows.groupby("country_code")["year"].nunique()
        countries_with_enough_history = observations_by_country[
            observations_by_country >= min_observations
        ]

        if countries_with_enough_history.empty:
            failures.append(
                {
                    "metric_id": metric_id,
                    "expected_min_observations_for_at_least_one_country": min_observations,
                    "max_observations_for_any_country": int(
                        observations_by_country.max()
                    ),
                }
            )

    assert failures == []


def test_each_country_has_minimum_metric_count(data_correctness_context) -> None:
    dataframe = data_correctness_context.dataframe
    minimums = _minimums()

    min_metrics_per_country = int(minimums["min_metrics_per_country"])

    metric_counts = dataframe.groupby("country_code")["metric_id"].nunique()
    sparse_countries = metric_counts[metric_counts < min_metrics_per_country]

    assert sparse_countries.empty, sparse_countries.to_dict()


def test_release_critical_metrics_are_not_too_stale(
    data_correctness_context,
) -> None:
    dataframe = data_correctness_context.dataframe.copy()
    section = _coverage_section(data_correctness_context)
    minimums = _minimums()

    critical_metrics = section.get("release_critical_metrics")
    if not critical_metrics:
        critical_metrics = section.get("metrics", [])

    max_staleness_years = int(minimums["max_latest_year_staleness_years"])
    dataset_max_year = int(pd.to_numeric(dataframe["year"], errors="coerce").max())

    failures: list[dict[str, object]] = []

    for metric_id in sorted(str(metric) for metric in critical_metrics):
        metric_rows = dataframe[dataframe["metric_id"].astype(str) == metric_id]
        if metric_rows.empty:
            continue

        metric_max_year = int(pd.to_numeric(metric_rows["year"], errors="coerce").max())
        staleness = dataset_max_year - metric_max_year

        if staleness > max_staleness_years:
            failures.append(
                {
                    "metric_id": metric_id,
                    "dataset_max_year": dataset_max_year,
                    "metric_max_year": metric_max_year,
                    "staleness_years": staleness,
                    "max_allowed_staleness_years": max_staleness_years,
                }
            )

    assert failures == []
