from __future__ import annotations

import json

from country_compare.data.catalog import (
    CATALOG_SCHEMA_VERSION,
    build_metadata_catalog,
    catalog_path_for_dataset,
    read_metadata_catalog,
    validate_metadata_catalog,
)
from country_compare.data.examples import build_example_metric_dataframe
from country_compare.data.publish import atomic_publish_metric_dataframe


def test_build_metadata_catalog_contains_selector_metadata() -> None:
    dataframe = build_example_metric_dataframe()
    catalog = build_metadata_catalog(dataframe, identity={"dataset_version": "test"})
    assert catalog["schema_version"] == CATALOG_SCHEMA_VERSION
    assert catalog["identity"] == {"dataset_version": "test"}
    assert catalog["countries"]
    assert catalog["metrics"]
    assert catalog["years"] == sorted(catalog["years"])
    assert catalog["dataset"]["row_count"] == len(dataframe)
    assert validate_metadata_catalog(catalog).valid is True


def test_atomic_publish_writes_readable_metadata_catalog(tmp_path) -> None:
    dataframe = build_example_metric_dataframe()
    dataset_path = tmp_path / "processed" / "metrics.parquet"
    publish_result = atomic_publish_metric_dataframe(
        dataframe, dataset_path=dataset_path
    )
    catalog_path = catalog_path_for_dataset(dataset_path)
    assert publish_result.catalog_path == str(catalog_path)
    assert catalog_path.exists()
    catalog = read_metadata_catalog(catalog_path)
    assert catalog.dataset["row_count"] == len(dataframe)
    assert catalog.identity["dataset_sha256"] == publish_result.sha256
    assert catalog.countries


def test_invalid_metadata_catalog_reports_shape_issues(tmp_path) -> None:
    catalog_path = tmp_path / "catalog.json"
    catalog_path.write_text(json.dumps({"schema_version": "bad"}), encoding="utf-8")
    validation = validate_metadata_catalog(json.loads(catalog_path.read_text()))
    assert validation.valid is False
    assert any("schema_version" in message for message in validation.messages)
