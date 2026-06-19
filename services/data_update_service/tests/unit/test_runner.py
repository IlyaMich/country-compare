from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd

from data_update_service.infrastructure.dataset_registry import InMemoryDatasetRegistry
from data_update_service.infrastructure.job_store import InMemoryJobStore
from data_update_service.infrastructure.locks import InMemorySourceLockManager
from data_update_service.orchestration.commands import RefreshCommand
from data_update_service.orchestration.runner import RunnerDependencies, run_refresh_job


class FakePipelineResult:
    def __init__(
        self,
        *,
        ok: bool,
        dataframe: pd.DataFrame | None = None,
        error: str | None = None,
    ) -> None:
        self.ok = ok
        self.canonical_dataframe = dataframe
        self.error = error
        self.validation_report = {"ok": ok}
        self.warnings: list[str] = []


class FakePipelineRunner:
    def __init__(self, result: FakePipelineResult) -> None:
        self.result = result
        self.called_with_audit_dir: Path | None = None

    def run(self, command: RefreshCommand, *, audit_dir: Path) -> FakePipelineResult:
        self.called_with_audit_dir = audit_dir
        return self.result


@dataclass(frozen=True, slots=True)
class FakeArtifact:
    dataset_version: str = "world_bank_2026-06-13T00-08-30Z_abcdef1"
    artifact_uri: str = "file:///tmp/artifact"
    parquet_sha256: str = "abcdef1234567890"
    validation_report_path: Path = Path("/tmp/artifact/validation_report.json")
    diff_report_json_path: Path = Path("/tmp/artifact/diff_report.json")


class FakeArtifactStore:
    def __init__(self) -> None:
        self.called = False

    def publish_package(self, **kwargs: Any) -> FakeArtifact:
        self.called = True
        return FakeArtifact()


class FakeDiffGenerator:
    def generate(self, dataframe: pd.DataFrame) -> Any:
        from data_update_service.orchestration.diff import generate_diff_report

        return generate_diff_report(dataframe)


def _dataframe() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"country_code": "ISR", "metric_id": "gdp", "year": 2024},
            {"country_code": "FRA", "metric_id": "gdp", "year": 2025},
        ]
    )


def _command(
    tmp_path: Path,
    *,
    dry_run: bool,
    publish: bool,
    promote: bool = False,
    promotion_channel: str | None = "staging",
) -> RefreshCommand:
    manifest_path = tmp_path / "manifest.yaml"
    manifest_path.write_text("sources: []\n", encoding="utf-8")
    return RefreshCommand.create(
        source_family="world_bank",
        manifest_path=manifest_path,
        dry_run=dry_run,
        publish=publish,
        promote=promote,
        promotion_channel=promotion_channel,
    )


def test_run_refresh_job_returns_dry_run_result_without_artifact(tmp_path) -> None:
    runner = FakePipelineRunner(FakePipelineResult(ok=True, dataframe=_dataframe()))
    artifact_store = FakeArtifactStore()
    deps = RunnerDependencies(
        pipeline_runner=runner,
        diff_generator=FakeDiffGenerator(),
        artifact_store=artifact_store,
        audit_root=tmp_path / "audit",
    )

    result = run_refresh_job(_command(tmp_path, dry_run=True, publish=False), deps)

    assert result.status == "dry_run_completed"
    assert result.row_count == 2
    assert result.country_count == 2
    assert result.metric_count == 1
    assert result.year_min == 2024
    assert result.year_max == 2025
    assert artifact_store.called is False


def test_run_refresh_job_publishes_artifact_when_requested(tmp_path) -> None:
    runner = FakePipelineRunner(FakePipelineResult(ok=True, dataframe=_dataframe()))
    artifact_store = FakeArtifactStore()
    deps = RunnerDependencies(
        pipeline_runner=runner,
        diff_generator=FakeDiffGenerator(),
        artifact_store=artifact_store,
        audit_root=tmp_path / "audit",
    )

    result = run_refresh_job(_command(tmp_path, dry_run=False, publish=True), deps)

    assert result.status == "completed"
    assert result.dataset_version == "world_bank_2026-06-13T00-08-30Z_abcdef1"
    assert result.artifact_uri == "file:///tmp/artifact"
    assert artifact_store.called is True


def test_run_refresh_job_fails_when_manifest_is_missing(tmp_path) -> None:
    command = RefreshCommand.create(
        source_family="world_bank",
        manifest_path=tmp_path / "missing.yaml",
        dry_run=True,
        publish=False,
    )
    deps = RunnerDependencies(
        pipeline_runner=FakePipelineRunner(
            FakePipelineResult(ok=True, dataframe=_dataframe())
        ),
        diff_generator=FakeDiffGenerator(),
        artifact_store=None,
        audit_root=tmp_path / "audit",
    )

    result = run_refresh_job(command, deps)

    assert result.status == "failed_non_retryable"
    assert result.error_code == "manifest_not_found"


class CountingPipelineRunner(FakePipelineRunner):
    def __init__(self, result: FakePipelineResult) -> None:
        super().__init__(result)
        self.call_count = 0

    def run(self, command: RefreshCommand, *, audit_dir: Path) -> FakePipelineResult:
        self.call_count += 1
        return super().run(command, audit_dir=audit_dir)


def test_run_refresh_job_returns_stored_terminal_result_for_duplicate_command(
    tmp_path,
) -> None:
    runner = CountingPipelineRunner(FakePipelineResult(ok=True, dataframe=_dataframe()))
    job_store = InMemoryJobStore()
    deps = RunnerDependencies(
        pipeline_runner=runner,
        diff_generator=FakeDiffGenerator(),
        artifact_store=FakeArtifactStore(),
        audit_root=tmp_path / "audit",
        job_store=job_store,
        source_locks=InMemorySourceLockManager(),
    )
    command = _command(tmp_path, dry_run=True, publish=False)

    first = run_refresh_job(command, deps)
    second = run_refresh_job(command, deps)

    assert first == second
    assert runner.call_count == 1
    stored_job = job_store.get_job(command.job_id)
    assert stored_job is not None
    assert stored_job.status == "dry_run_completed"


def test_run_refresh_job_returns_retryable_failure_when_source_is_locked(
    tmp_path,
) -> None:
    runner = CountingPipelineRunner(FakePipelineResult(ok=True, dataframe=_dataframe()))
    source_locks = InMemorySourceLockManager()
    deps = RunnerDependencies(
        pipeline_runner=runner,
        diff_generator=FakeDiffGenerator(),
        artifact_store=FakeArtifactStore(),
        audit_root=tmp_path / "audit",
        job_store=InMemoryJobStore(),
        source_locks=source_locks,
    )
    command = _command(tmp_path, dry_run=True, publish=False)

    with source_locks.acquire(command.source_family, "other-job"):
        result = run_refresh_job(command, deps)

    assert result.status == "failed_retryable"
    assert result.error_code == "source_lock_unavailable"
    assert runner.call_count == 0


def test_run_refresh_job_promotes_dataset_after_publish(tmp_path) -> None:
    runner = CountingPipelineRunner(FakePipelineResult(ok=True, dataframe=_dataframe()))
    registry = InMemoryDatasetRegistry()
    job_store = InMemoryJobStore()
    deps = RunnerDependencies(
        pipeline_runner=runner,
        diff_generator=FakeDiffGenerator(),
        artifact_store=FakeArtifactStore(),
        audit_root=tmp_path / "audit",
        job_store=job_store,
        source_locks=InMemorySourceLockManager(),
        dataset_registry=registry,
    )
    command = _command(
        tmp_path,
        dry_run=False,
        publish=True,
        promote=True,
        promotion_channel="staging",
    )

    result = run_refresh_job(command, deps)

    channel = registry.get_channel(source_family="world_bank", channel="staging")
    stored_job = job_store.get_job(command.job_id)

    assert result.status == "completed"
    assert channel is not None
    assert channel.dataset_version == result.dataset_version
    assert channel.promoted_by == command.requested_by
    assert stored_job is not None
    assert stored_job.status == "completed"
    assert "promotion_completed" in stored_job.status_history


def test_run_refresh_job_fails_promote_without_registry(tmp_path) -> None:
    runner = CountingPipelineRunner(FakePipelineResult(ok=True, dataframe=_dataframe()))
    artifact_store = FakeArtifactStore()
    deps = RunnerDependencies(
        pipeline_runner=runner,
        diff_generator=FakeDiffGenerator(),
        artifact_store=artifact_store,
        audit_root=tmp_path / "audit",
        job_store=InMemoryJobStore(),
        source_locks=InMemorySourceLockManager(),
        dataset_registry=None,
    )
    command = _command(
        tmp_path,
        dry_run=False,
        publish=True,
        promote=True,
        promotion_channel="staging",
    )

    result = run_refresh_job(command, deps)

    assert result.status == "failed_non_retryable"
    assert result.error_code == "dataset_registry_not_configured"
    assert artifact_store.called is False


def test_run_refresh_job_registers_dataset_metadata_after_publish(tmp_path) -> None:
    runner = CountingPipelineRunner(FakePipelineResult(ok=True, dataframe=_dataframe()))
    registry = InMemoryDatasetRegistry()
    deps = RunnerDependencies(
        pipeline_runner=runner,
        diff_generator=FakeDiffGenerator(),
        artifact_store=FakeArtifactStore(),
        audit_root=tmp_path / "audit",
        job_store=InMemoryJobStore(),
        source_locks=InMemorySourceLockManager(),
        dataset_registry=registry,
    )
    command = _command(tmp_path, dry_run=False, publish=True)

    result = run_refresh_job(command, deps)

    records = registry.list_dataset_versions(source_family="world_bank")
    assert result.status == "completed"
    assert len(records) == 1
    assert records[0].dataset_version == result.dataset_version
    assert records[0].created_by_job_id == command.job_id
    assert records[0].row_count == 2


def test_run_refresh_job_fails_dry_run_without_outputs(tmp_path) -> None:
    runner = FakePipelineRunner(
        FakePipelineResult(
            ok=False,
            error="no valid canonical outputs were produced by the pipeline",
        )
    )
    artifact_store = FakeArtifactStore()
    deps = RunnerDependencies(
        pipeline_runner=runner,
        diff_generator=FakeDiffGenerator(),
        artifact_store=artifact_store,
        audit_root=tmp_path / "audit",
    )

    result = run_refresh_job(_command(tmp_path, dry_run=True, publish=False), deps)

    assert result.status == "failed_non_retryable"
    assert result.error_code == "processing_failed"
    assert (
        result.error_message
        == "no valid canonical outputs were produced by the pipeline"
    )


def test_run_refresh_job_fails_non_dry_run_without_outputs(tmp_path) -> None:
    runner = FakePipelineRunner(
        FakePipelineResult(
            ok=False,
            error="no valid canonical outputs were produced by the pipeline",
        )
    )
    artifact_store = FakeArtifactStore()
    deps = RunnerDependencies(
        pipeline_runner=runner,
        diff_generator=FakeDiffGenerator(),
        artifact_store=artifact_store,
        audit_root=tmp_path / "audit",
    )

    result = run_refresh_job(_command(tmp_path, dry_run=False, publish=True), deps)

    assert result.status == "failed_non_retryable"
    assert result.error_code == "processing_failed"
    assert (
        result.error_message
        == "no valid canonical outputs were produced by the pipeline"
    )
    assert artifact_store.called is False
