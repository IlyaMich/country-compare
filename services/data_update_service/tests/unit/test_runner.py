from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd

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


def _command(tmp_path: Path, *, dry_run: bool, publish: bool) -> RefreshCommand:
    manifest_path = tmp_path / "manifest.yaml"
    manifest_path.write_text("sources: []\n", encoding="utf-8")
    return RefreshCommand.create(
        source_family="world_bank",
        manifest_path=manifest_path,
        dry_run=dry_run,
        publish=publish,
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
