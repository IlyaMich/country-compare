from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from country_compare.config.loader import load_metrics_config
from country_compare.paths import METRICS_CONFIG_PATH

pytestmark = pytest.mark.integration


def _build_metric_catalog(dataframe: pd.DataFrame) -> pd.DataFrame:
    return (
        dataframe.groupby("metric_id", dropna=False)
        .agg(
            metric_name=("metric_name", "first"),
            unit=("unit", "first"),
            category=("category", "first"),
            source_name=("source_name", "first"),
            source_url=("source_url", "first"),
            higher_is_better=("higher_is_better", "first"),
            row_count=("metric_id", "size"),
            country_count=("country_code", "nunique"),
            year_min=("year", "min"),
            year_max=("year", "max"),
        )
        .reset_index()
        .sort_values("metric_id")
        .reset_index(drop=True)
    )


def test_derived_metadata_catalog_matches_actual_dataset(
    data_correctness_context,
) -> None:
    dataframe = data_correctness_context.dataframe
    catalog = _build_metric_catalog(dataframe)

    assert len(catalog) == dataframe["metric_id"].nunique()
    assert catalog["row_count"].sum() == len(dataframe)
    assert (catalog["country_count"] > 0).all()
    assert (catalog["year_min"] <= catalog["year_max"]).all()
    assert catalog["metric_name"].notna().all()
    assert catalog["unit"].notna().all()
    assert catalog["category"].notna().all()
    assert catalog["source_name"].notna().all()
    assert catalog["source_url"].notna().all()


def test_metadata_catalog_year_ranges_match_dataset_rows(
    data_correctness_context,
) -> None:
    dataframe = data_correctness_context.dataframe
    catalog = _build_metric_catalog(dataframe)

    mismatches: list[dict[str, object]] = []

    for row in catalog.itertuples(index=False):
        metric_rows = dataframe[dataframe["metric_id"] == row.metric_id]

        actual_min_year = int(metric_rows["year"].min())
        actual_max_year = int(metric_rows["year"].max())

        if int(row.year_min) != actual_min_year or int(row.year_max) != actual_max_year:
            mismatches.append(
                {
                    "metric_id": row.metric_id,
                    "catalog_year_min": int(row.year_min),
                    "actual_year_min": actual_min_year,
                    "catalog_year_max": int(row.year_max),
                    "actual_year_max": actual_max_year,
                }
            )

    assert mismatches == []


def test_dataset_metadata_matches_metrics_config_when_applicable(
    data_correctness_context,
) -> None:
    if data_correctness_context.is_example_dataset:
        pytest.skip("Example dataset intentionally does not use config/metrics.yaml.")

    config_path = Path(METRICS_CONFIG_PATH)
    if not config_path.exists():
        pytest.skip(f"No metrics config found at {config_path}.")

    dataframe = data_correctness_context.dataframe
    catalog = _build_metric_catalog(dataframe)
    metrics_config = load_metrics_config(config_path)

    catalog_by_metric = {
        str(row.metric_id): row
        for row in catalog.itertuples(index=False)
    }

    overlapping_metric_ids = sorted(set(catalog_by_metric) & set(metrics_config.metrics))
    assert overlapping_metric_ids, "No overlap between dataset metadata and metrics config."

    mismatches: list[dict[str, object]] = []

    for metric_id in overlapping_metric_ids:
        row = catalog_by_metric[metric_id]
        configured = metrics_config.metrics[metric_id]

        checks = {
            "unit": (str(row.unit), configured.unit),
            "category": (str(row.category), configured.category),
            "higher_is_better": (bool(row.higher_is_better), configured.higher_is_better),
        }

        for field_name, (actual, expected) in checks.items():
            if expected is not None and actual != expected:
                mismatches.append(
                    {
                        "metric_id": metric_id,
                        "field": field_name,
                        "actual": actual,
                        "expected": expected,
                    }
                )

    assert mismatches == []