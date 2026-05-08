from __future__ import annotations

import json

from matplotlib.pylab import identity

from country_compare.data.examples import build_example_metric_dataframe
from country_compare.data.manifest import build_manifest_from_dataframe_or_file
from country_compare.data.publish import atomic_publish_metric_dataframe
from country_compare.services.dataset_service import DatasetService


def test_dataset_summary_reports_manifest_and_dataset_identity(
    fake_app_context,
) -> None:
    dataframe = build_example_metric_dataframe()
    atomic_publish_metric_dataframe(dataframe, dataset_path=fake_app_context.store_path)

    service = DatasetService(fake_app_context)
    summary = service.get_dataset_summary()
    identity = service.get_dataset_identity(dataframe)

    assert summary.exists is True
    assert summary.schema_valid is True
    assert summary.manifest_exists is True
    assert summary.manifest_valid is True
    assert summary.manifest_schema_version == "country-compare-metric-dataset-v1"
    assert summary.dataset_checksum is not None
    expected_dataset_version = str(dataframe["dataset_version"].dropna().iloc[0])
    assert summary.dataset_versions == (expected_dataset_version,)
    assert identity["dataset_version"] == expected_dataset_version
    assert identity["dataset_sha256"] == summary.dataset_checksum
    assert identity["dataset_file"] == "metrics.parquet"


def test_dataset_summary_fails_manifest_validation_when_manifest_is_stale(
    fake_app_context,
) -> None:
    dataframe = build_example_metric_dataframe()
    fake_app_context.store_path.parent.mkdir(parents=True, exist_ok=True)
    dataframe.to_parquet(fake_app_context.store_path, index=False)
    manifest_path = fake_app_context.store_path.with_name("metrics_manifest.json")
    manifest = build_manifest_from_dataframe_or_file(
        dataframe=dataframe,
        dataset_path=fake_app_context.store_path,
        dataset_file=fake_app_context.store_path.name,
    )
    manifest["row_count"] = 1
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    summary = DatasetService(fake_app_context).get_dataset_summary()

    assert summary.exists is True
    assert summary.schema_valid is True
    assert summary.manifest_valid is False
    assert summary.manifest_issue_count >= 1
    assert any("row count" in message for message in summary.manifest_issues)
