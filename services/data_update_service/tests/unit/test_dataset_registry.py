from __future__ import annotations

from pathlib import Path

from data_update_service.infrastructure.dataset_registry import (
    FilesystemDatasetRegistry,
    InMemoryDatasetRegistry,
)
from data_update_service.orchestration.commands import RefreshCommand
from data_update_service.orchestration.results import RefreshResult


class FakeArtifact:
    dataset_version = "world_bank_2026-06-13T00-08-30Z_abcdef1"
    artifact_uri = "file:///tmp/artifact"
    parquet_sha256 = "abcdef1234567890"
    validation_report_path = Path("/tmp/artifact/validation_report.json")
    diff_report_json_path = Path("/tmp/artifact/diff_report.json")


def _command() -> RefreshCommand:
    return RefreshCommand.create(
        source_family="world_bank",
        manifest_path="manifest.yaml",
        command_id="cmd-1",
        job_id="job-1",
        idempotency_key="idem-1",
        correlation_id="corr-1",
    )


def _result() -> RefreshResult:
    return RefreshResult(
        job_id="job-1",
        command_id="cmd-1",
        source_family="world_bank",
        status="completed",
        dataset_version=FakeArtifact.dataset_version,
        artifact_uri=FakeArtifact.artifact_uri,
        validation_report_uri="file:///tmp/artifact/validation_report.json",
        diff_report_uri="file:///tmp/artifact/diff_report.json",
        row_count=10,
        country_count=2,
        metric_count=3,
        year_min=2020,
        year_max=2025,
    )


def test_in_memory_dataset_registry_registers_metadata() -> None:
    registry = InMemoryDatasetRegistry()

    record = registry.register_dataset_version(
        command=_command(),
        artifact=FakeArtifact(),
        result=_result(),
    )

    assert record.dataset_version == FakeArtifact.dataset_version
    assert record.row_count == 10
    assert registry.get_dataset_version(FakeArtifact.dataset_version) == record
    assert registry.list_dataset_versions(source_family="world_bank") == [record]


def test_filesystem_dataset_registry_persists_metadata(tmp_path) -> None:
    registry = FilesystemDatasetRegistry(tmp_path)
    record = registry.register_dataset_version(
        command=_command(),
        artifact=FakeArtifact(),
        result=_result(),
    )

    reloaded = FilesystemDatasetRegistry(tmp_path).get_dataset_version(
        FakeArtifact.dataset_version
    )

    assert reloaded == record
    assert (tmp_path / "world_bank" / "registry" / "dataset_versions.json").exists()
