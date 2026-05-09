from __future__ import annotations

import json

from country_compare.data.examples import build_example_metric_dataframe
from country_compare.data.manifest import (
    DATASET_SCHEMA_VERSION,
    build_manifest_from_dataframe_or_file,
    validate_manifest_against_dataset,
)
from country_compare.data.publish import atomic_publish_metric_dataframe


def test_build_manifest_and_validate_against_dataset(tmp_path) -> None:
    dataframe = build_example_metric_dataframe()
    dataset_path = tmp_path / "metrics.parquet"
    dataframe.to_parquet(dataset_path, index=False)
    manifest_path = tmp_path / "metrics_manifest.json"

    manifest = build_manifest_from_dataframe_or_file(
        dataframe=dataframe,
        dataset_path=dataset_path,
        dataset_file=dataset_path.name,
    )
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    result = validate_manifest_against_dataset(
        manifest_path=manifest_path,
        dataset_path=dataset_path,
    )

    assert result.valid is True
    assert result.error_count == 0
    assert result.dataset_summary["row_count"] == len(dataframe)
    assert manifest["schema_version"] == DATASET_SCHEMA_VERSION
    assert manifest["dataset_file"] == "metrics.parquet"
    assert manifest["sha256"]


def test_validate_manifest_reports_hash_mismatch(tmp_path) -> None:
    dataframe = build_example_metric_dataframe()
    dataset_path = tmp_path / "metrics.parquet"
    dataframe.to_parquet(dataset_path, index=False)
    manifest = build_manifest_from_dataframe_or_file(
        dataframe=dataframe,
        dataset_path=dataset_path,
        dataset_file=dataset_path.name,
    )
    manifest["sha256"] = "0" * 64
    manifest_path = tmp_path / "metrics_manifest.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    result = validate_manifest_against_dataset(
        manifest_path=manifest_path,
        dataset_path=dataset_path,
    )

    assert result.valid is False
    assert any(issue.code == "hash_mismatch" for issue in result.issues)
    assert "Dataset hash does not match manifest sha256." in result.messages


def test_validate_manifest_reports_missing_manifest(tmp_path) -> None:
    dataframe = build_example_metric_dataframe()
    dataset_path = tmp_path / "metrics.parquet"
    dataframe.to_parquet(dataset_path, index=False)

    result = validate_manifest_against_dataset(
        manifest_path=tmp_path / "metrics_manifest.json",
        dataset_path=dataset_path,
    )

    assert result.valid is False
    assert any(issue.code == "manifest_missing" for issue in result.issues)


def test_atomic_publish_writes_dataset_and_matching_manifest(tmp_path) -> None:
    dataframe = build_example_metric_dataframe()
    dataset_path = tmp_path / "processed" / "metrics.parquet"

    publish_result = atomic_publish_metric_dataframe(
        dataframe,
        dataset_path=dataset_path,
        pipeline_version="test-pipeline",
    )

    manifest_path = tmp_path / "processed" / "metrics_manifest.json"
    assert dataset_path.exists()
    assert manifest_path.exists()
    assert (tmp_path / "processed" / "catalog.json").exists()
    assert publish_result.row_count == len(dataframe)
    assert publish_result.manifest["pipeline_version"] == "test-pipeline"

    validation = validate_manifest_against_dataset(
        manifest_path=manifest_path,
        dataset_path=dataset_path,
    )
    assert validation.valid is True
