from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd

from data_update_service.orchestration.artifact_package import S3ArtifactStore
from data_update_service.orchestration.commands import RefreshCommand
from data_update_service.orchestration.diff import DatasetDiffReport, DatasetSummary
from data_update_service.orchestration.results import RefreshResult


@dataclass(frozen=True, slots=True)
class UploadCall:
    filename: str
    bucket: str
    key: str
    extra_args: dict[str, Any]


class FakeS3Client:
    def __init__(self) -> None:
        self.uploads: list[UploadCall] = []

    def upload_file(
        self,
        *,
        Filename: str,
        Bucket: str,
        Key: str,
        ExtraArgs: dict[str, Any],
    ) -> None:
        self.uploads.append(
            UploadCall(
                filename=Filename,
                bucket=Bucket,
                key=Key,
                extra_args=ExtraArgs,
            )
        )


def _command() -> RefreshCommand:
    return RefreshCommand.create(
        source_family="world_bank",
        manifest_path="config/source_manifests/world_bank_real_data.yaml",
        mode="full_refresh",
        acquisition_mode="local",
        dry_run=False,
        publish=True,
        promote=False,
        promotion_channel="staging",
        requested_by="test",
    )


def _dataframe() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "country_code": "ISR",
                "country_name": "Israel",
                "metric_id": "gdp_per_capita",
                "metric_name": "GDP per capita",
                "value": 1.0,
                "year": 2024,
                "unit": "USD",
                "source_name": "Test",
                "source_url": "https://example.com",
                "higher_is_better": True,
                "category": "economy",
            }
        ]
    )


def test_s3_artifact_store_uploads_immutable_package(tmp_path: Path) -> None:
    command = _command()
    dataframe = _dataframe()
    diff_report = DatasetDiffReport(
        summary=DatasetSummary(
            row_count=1,
            country_count=1,
            metric_count=1,
            year_min=2024,
            year_max=2024,
        )
    )
    result = RefreshResult(
        job_id=command.job_id,
        command_id=command.command_id,
        source_family=command.source_family,
        status="completed",
        row_count=1,
        country_count=1,
        metric_count=1,
        year_min=2024,
        year_max=2024,
    )

    client = FakeS3Client()
    store = S3ArtifactStore(
        bucket="country-compare-datasets",
        prefix="datasets",
        endpoint_url="http://localhost:9000",
        region_name="us-east-1",
        access_key_id="minio",
        secret_access_key="minio123",
        local_staging_root=tmp_path / "staging",
        client=client,
    )

    artifact = store.publish_package(
        command=command,
        dataframe=dataframe,
        validation_report={"ok": True},
        diff_report=diff_report,
        result_payload=result,
    )

    uploaded_keys = {upload.key for upload in client.uploads}

    assert artifact.artifact_uri.startswith(
        f"s3://country-compare-datasets/datasets/world_bank/versions/{artifact.dataset_version}/"
    )
    assert artifact.validation_report_uri is not None
    assert artifact.validation_report_uri.endswith("/validation_report.json")
    assert artifact.diff_report_json_uri is not None
    assert artifact.diff_report_json_uri.endswith("/diff_report.json")

    expected_files = {
        "metrics.parquet",
        "metrics_manifest.json",
        "catalog.json",
        "validation_report.json",
        "diff_report.json",
        "diff_report.md",
        "source_audit.json",
        "refresh_command.json",
        "refresh_result.json",
    }

    for filename in expected_files:
        assert (
            f"datasets/world_bank/versions/{artifact.dataset_version}/{filename}"
            in uploaded_keys
        )

    assert all(upload.bucket == "country-compare-datasets" for upload in client.uploads)
