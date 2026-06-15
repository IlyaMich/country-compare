from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd
from country_compare.pipelines.acquisition.snapshot import (
    RetryableSourceSnapshotAcquisitionError,
    SourceSnapshotAcquisitionError,
)

from data_update_service.orchestration.commands import RefreshCommand
from data_update_service.orchestration.diff import DatasetDiffReport
from data_update_service.orchestration.runner import RunnerDependencies, run_refresh_job


class NeverCalledPipelineRunner:
    def run(
        self,
        command: RefreshCommand,
        *,
        audit_dir: Path,
        raw_root: Path | None = None,
    ) -> Any:
        raise AssertionError("pipeline should not run after acquisition failure")


class NoopDiffGenerator:
    def generate(self, dataframe: pd.DataFrame) -> DatasetDiffReport:
        raise AssertionError("diff should not run after acquisition failure")


class RetryableFailingSourceAcquirer:
    def acquire(self, command: RefreshCommand) -> Any:
        raise RetryableSourceSnapshotAcquisitionError("temporary World Bank failure")


class NonRetryableFailingSourceAcquirer:
    def acquire(self, command: RefreshCommand) -> Any:
        raise SourceSnapshotAcquisitionError("invalid World Bank manifest")


def test_run_refresh_job_classifies_retryable_source_acquisition_failure(
    tmp_path: Path,
) -> None:
    command = _command(tmp_path)
    deps = RunnerDependencies(
        pipeline_runner=NeverCalledPipelineRunner(),
        diff_generator=NoopDiffGenerator(),
        source_acquirer=RetryableFailingSourceAcquirer(),
        audit_root=tmp_path / "audit",
    )

    result = run_refresh_job(command, deps)

    assert result.status == "failed_retryable"
    assert result.error_code == "source_acquisition_retryable"
    assert result.error_message == "temporary World Bank failure"


def test_run_refresh_job_classifies_non_retryable_source_acquisition_failure(
    tmp_path: Path,
) -> None:
    command = _command(tmp_path)
    deps = RunnerDependencies(
        pipeline_runner=NeverCalledPipelineRunner(),
        diff_generator=NoopDiffGenerator(),
        source_acquirer=NonRetryableFailingSourceAcquirer(),
        audit_root=tmp_path / "audit",
    )

    result = run_refresh_job(command, deps)

    assert result.status == "failed_non_retryable"
    assert result.error_code == "source_acquisition_failed"
    assert result.error_message == "invalid World Bank manifest"


def _command(tmp_path: Path) -> RefreshCommand:
    manifest_path = tmp_path / "manifest.yaml"
    manifest_path.write_text("sources: []\n", encoding="utf-8")
    return RefreshCommand.create(
        source_family="world_bank",
        manifest_path=manifest_path,
        acquisition_mode="remote",
        dry_run=True,
        publish=False,
    )
