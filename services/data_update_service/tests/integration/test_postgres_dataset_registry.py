from __future__ import annotations

import os
from pathlib import Path
from uuid import uuid4

import pytest

from data_update_service.infrastructure.postgres import (
    PostgresDatasetRegistry,
    PostgresJobStore,
)
from data_update_service.orchestration.artifact_package import ArtifactPackage
from data_update_service.orchestration.commands import RefreshCommand
from data_update_service.orchestration.results import RefreshResult

pytestmark = pytest.mark.integration


def _database_url() -> str:
    value = os.getenv("DATA_UPDATE_TEST_DATABASE_URL") or os.getenv(
        "DATA_UPDATE_DATABASE_URL"
    )
    if not value:
        pytest.skip(
            "set DATA_UPDATE_TEST_DATABASE_URL or DATA_UPDATE_DATABASE_URL "
            "to run Postgres integration tests"
        )
    return value


def _command() -> RefreshCommand:
    return RefreshCommand.create(
        source_family="world_bank",
        manifest_path="config/source_manifests/world_bank_real_data.yaml",
        command_id="cmd-postgres-registry-1",
        job_id="job-postgres-registry-1",
        idempotency_key="idem-postgres-registry-1",
        correlation_id="corr-postgres-registry-1",
        requested_by="pytest",
    )


def _artifact(tmp_path: Path) -> ArtifactPackage:
    suffix = uuid4().hex[:8]
    artifact_dir = tmp_path / "artifact"
    artifact_dir.mkdir()

    metrics_path = artifact_dir / "metrics.parquet"
    validation_report_path = artifact_dir / "validation_report.json"
    diff_report_json_path = artifact_dir / "diff_report.json"
    diff_report_markdown_path = artifact_dir / "diff_report.md"
    command_path = artifact_dir / "refresh_command.json"
    result_path = artifact_dir / "refresh_result.json"
    manifest_path = artifact_dir / "metrics_manifest.json"
    catalog_path = artifact_dir / "catalog.json"

    for path in (
        metrics_path,
        validation_report_path,
        diff_report_json_path,
        diff_report_markdown_path,
        command_path,
        result_path,
        manifest_path,
        catalog_path,
    ):
        path.write_text(path.name, encoding="utf-8")

    return ArtifactPackage(
        dataset_version=f"world_bank_2026-06-19T00-00-00Z_{suffix}",
        artifact_dir=artifact_dir,
        artifact_uri=artifact_dir.resolve().as_uri(),
        parquet_sha256=f"{suffix}1234567890",
        metrics_path=metrics_path,
        validation_report_path=validation_report_path,
        diff_report_json_path=diff_report_json_path,
        diff_report_markdown_path=diff_report_markdown_path,
        command_path=command_path,
        result_path=result_path,
    )


def _result(artifact: ArtifactPackage) -> RefreshResult:
    return RefreshResult(
        job_id="job-postgres-registry-1",
        command_id="cmd-postgres-registry-1",
        source_family="world_bank",
        status="completed",
        dataset_version=artifact.dataset_version,
        artifact_uri=artifact.artifact_uri,
        validation_report_uri=artifact.validation_report_path.as_uri(),
        diff_report_uri=artifact.diff_report_json_path.as_uri(),
        row_count=10,
        country_count=2,
        metric_count=3,
        year_min=2020,
        year_max=2025,
    )


def test_postgres_dataset_registry_registers_version(tmp_path: Path) -> None:
    database_url = _database_url()
    command = _command()
    artifact = _artifact(tmp_path)

    job_store = PostgresJobStore(database_url, initialize_schema=True)
    registry = PostgresDatasetRegistry(database_url, initialize_schema=True)

    job_store.create_or_get_job(command)

    record = registry.register_dataset_version(
        command=command,
        artifact=artifact,
        result=_result(artifact),
    )

    reloaded = registry.get_dataset_version(artifact.dataset_version)

    assert reloaded == record
    assert record.dataset_version == artifact.dataset_version
    assert record.source_family == "world_bank"
    assert record.artifact_uri == artifact.artifact_uri
    assert record.parquet_sha256 == artifact.parquet_sha256
    assert record.manifest_sha256
    assert record.catalog_sha256

    records = registry.list_dataset_versions(source_family="world_bank")
    assert record in records


def test_postgres_dataset_registry_promotes_channel(tmp_path: Path) -> None:
    database_url = _database_url()
    command = RefreshCommand.create(
        source_family="world_bank",
        manifest_path="config/source_manifests/world_bank_real_data.yaml",
        command_id="cmd-postgres-registry-2",
        job_id="job-postgres-registry-2",
        idempotency_key="idem-postgres-registry-2",
        correlation_id="corr-postgres-registry-2",
        requested_by="pytest",
    )
    artifact = _artifact(tmp_path)

    job_store = PostgresJobStore(database_url, initialize_schema=True)
    registry = PostgresDatasetRegistry(database_url, initialize_schema=True)

    job_store.create_or_get_job(command)
    registry.register_dataset_version(
        command=command,
        artifact=artifact,
        result=RefreshResult(
            job_id=command.job_id,
            command_id=command.command_id,
            source_family=command.source_family,
            status="completed",
            dataset_version=artifact.dataset_version,
            artifact_uri=artifact.artifact_uri,
            validation_report_uri=artifact.validation_report_path.as_uri(),
            diff_report_uri=artifact.diff_report_json_path.as_uri(),
            row_count=10,
            country_count=2,
            metric_count=3,
            year_min=2020,
            year_max=2025,
        ),
    )

    channel = registry.promote_dataset_version(
        dataset_version=artifact.dataset_version,
        channel="staging",
        promoted_by="pytest",
    )

    assert channel.channel == "staging"
    assert channel.source_family == "world_bank"
    assert channel.dataset_version == artifact.dataset_version
    assert channel.artifact_uri == artifact.artifact_uri
    assert channel.parquet_sha256 == artifact.parquet_sha256
    assert channel.promoted_by == "pytest"

    assert (
        registry.get_channel(
            source_family="world_bank",
            channel="staging",
        )
        == channel
    )
    channels = registry.list_channels(source_family="world_bank")
    matching_channels = [
        item
        for item in channels
        if item.channel == channel.channel
        and item.dataset_version == channel.dataset_version
    ]

    assert matching_channels == [channel]


def test_postgres_dataset_registry_rejects_unknown_promotion() -> None:
    database_url = _database_url()
    registry = PostgresDatasetRegistry(database_url, initialize_schema=True)

    with pytest.raises(KeyError, match="unknown dataset version"):
        registry.promote_dataset_version(
            dataset_version="missing",
            channel="staging",
            promoted_by="pytest",
        )
