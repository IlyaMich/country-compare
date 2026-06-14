from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

import pandas as pd

from data_update_service.infrastructure.dataset_registry import (
    DatasetRegistry,
    FilesystemDatasetRegistry,
)
from data_update_service.infrastructure.job_store import (
    InMemoryJobStore,
    JobStore,
    JobStatus,
)
from data_update_service.infrastructure.locks import (
    InMemorySourceLockManager,
    SourceLockManager,
    SourceLockUnavailableError,
)
from data_update_service.orchestration.artifact_package import (
    ArtifactPackage,
    FilesystemArtifactStore,
)
from data_update_service.orchestration.commands import RefreshCommand
from data_update_service.orchestration.diff import DatasetDiffReport, generate_diff_report
from data_update_service.orchestration.results import RefreshResult
from data_update_service.settings import DataUpdateSettings


class PipelineRunner(Protocol):
    def run(self, command: RefreshCommand, *, audit_dir: Path) -> Any:
        """Run the Country Compare processing path and return a ProcessingResult-like object."""


class DiffGenerator(Protocol):
    def generate(self, dataframe: pd.DataFrame) -> DatasetDiffReport:
        """Generate a diff report for the canonical dataframe."""


class ArtifactStore(Protocol):
    def publish_package(
        self,
        *,
        command: RefreshCommand,
        dataframe: pd.DataFrame,
        validation_report: Any,
        diff_report: DatasetDiffReport,
        result_payload: Any,
    ) -> ArtifactPackage:
        """Publish an immutable artifact package and return an ArtifactPackage."""


class CountryComparePipelineRunner:
    """Adapter around the existing framework-neutral manifest pipeline."""

    def __init__(self, *, metrics_config_path: Path | None = None) -> None:
        self.metrics_config_path = metrics_config_path

    def run(self, command: RefreshCommand, *, audit_dir: Path) -> Any:
        from country_compare.config.loader import load_metrics_config
        from country_compare.paths import METRICS_CONFIG_PATH
        from country_compare.pipelines.runners import run_processing_manifest

        metrics_config_path = self.metrics_config_path or METRICS_CONFIG_PATH
        metrics_config = load_metrics_config(metrics_config_path)

        # `command.publish` means publish an immutable data-update artifact package.
        # It intentionally does not mutate the default `data/processed/metrics.parquet`.
        return run_processing_manifest(
            command.manifest_path,
            publish=False,
            write_metric_dataset=False,
            validate_against_config=True,
            metrics_config=metrics_config,
            write_audit_artifacts=True,
            output_dir=audit_dir,
        )


class DefaultDiffGenerator:
    def generate(self, dataframe: pd.DataFrame) -> DatasetDiffReport:
        return generate_diff_report(dataframe)


@dataclass(frozen=True, slots=True)
class RunnerDependencies:
    pipeline_runner: PipelineRunner
    diff_generator: DiffGenerator
    artifact_store: ArtifactStore | None = None
    audit_root: Path = Path("data/audit/data_update")
    job_store: JobStore | None = None
    source_locks: SourceLockManager | None = None
    dataset_registry: DatasetRegistry | None = None

    @classmethod
    def local_defaults(cls, settings: DataUpdateSettings | None = None) -> RunnerDependencies:
        resolved = settings or DataUpdateSettings()
        return cls(
            pipeline_runner=CountryComparePipelineRunner(),
            diff_generator=DefaultDiffGenerator(),
            artifact_store=FilesystemArtifactStore(resolved.artifact_root),
            audit_root=resolved.audit_root,
            job_store=InMemoryJobStore(),
            source_locks=InMemorySourceLockManager(ttl_seconds=resolved.source_lock_ttl_seconds),
            dataset_registry=FilesystemDatasetRegistry(resolved.artifact_root),
        )


def run_refresh_job(
    command: RefreshCommand,
    dependencies: RunnerDependencies | None = None,
) -> RefreshResult:
    """Run a refresh job through the shared orchestration path.

    Milestone 2 adds the operational shell that the future Kafka worker needs:
    idempotent job creation, source-family locking, job status transitions, and
    dataset-version metadata registration. Kafka, Postgres, retries, and the
    private admin API still wrap this shared function later instead of changing
    the refresh behavior.
    """

    deps = dependencies or RunnerDependencies.local_defaults()
    job_record = None
    if deps.job_store is not None:
        job_record = deps.job_store.create_or_get_job(command)
        if job_record.is_terminal:
            stored_result = deps.job_store.result_for_job(job_record.job_id)
            if stored_result is not None:
                return stored_result

    audit_dir = deps.audit_root / command.source_family / command.job_id

    try:
        try:
            if deps.source_locks is None:
                return _execute_refresh(command, deps, audit_dir)
            with deps.source_locks.acquire(command.source_family, command.job_id):
                return _execute_refresh(command, deps, audit_dir)
        except SourceLockUnavailableError as exc:
            result = _failure(
                command,
                status="failed_retryable",
                error_code="source_lock_unavailable",
                error_message=str(exc),
            )
            _complete_job(deps, result)
            return result
    except Exception as exc:  # pragma: no cover - defensive wrapper for CLI ergonomics
        result = _failure(
            command,
            status="failed_non_retryable",
            error_code=exc.__class__.__name__,
            error_message=str(exc),
        )
        _complete_job(deps, result)
        return result


def _execute_refresh(
    command: RefreshCommand,
    deps: RunnerDependencies,
    audit_dir: Path,
) -> RefreshResult:
    _mark_running(deps, command.job_id)

    if not command.manifest.exists():
        result = _failure(
            command,
            status="failed_non_retryable",
            error_code="manifest_not_found",
            error_message=f"Manifest file not found: {command.manifest_path}",
        )
        _complete_job(deps, result)
        return result

    processing_result = deps.pipeline_runner.run(command, audit_dir=audit_dir)
    if not bool(getattr(processing_result, "ok", False)):
        result = _processing_failure(command, processing_result)
        _complete_job(deps, result)
        return result

    _update_status(deps, command.job_id, "pipeline_completed")
    dataframe = getattr(processing_result, "canonical_dataframe", None)
    if not isinstance(dataframe, pd.DataFrame):
        result = _failure(
            command,
            status="failed_non_retryable",
            error_code="missing_canonical_dataframe",
            error_message="Processing completed without a canonical dataframe.",
        )
        _complete_job(deps, result)
        return result

    diff_report = deps.diff_generator.generate(dataframe)
    summary = diff_report.summary
    warnings = _collect_warnings(processing_result)
    _update_status(deps, command.job_id, "validation_passed")

    if diff_report.no_changes:
        result = RefreshResult(
            job_id=command.job_id,
            command_id=command.command_id,
            source_family=command.source_family,
            status="completed_no_changes",
            row_count=summary.row_count,
            country_count=summary.country_count,
            metric_count=summary.metric_count,
            year_min=summary.year_min,
            year_max=summary.year_max,
            warnings=warnings,
        )
        _complete_job(deps, result)
        return result

    if command.dry_run or not command.publish:
        result = RefreshResult(
            job_id=command.job_id,
            command_id=command.command_id,
            source_family=command.source_family,
            status="dry_run_completed",
            row_count=summary.row_count,
            country_count=summary.country_count,
            metric_count=summary.metric_count,
            year_min=summary.year_min,
            year_max=summary.year_max,
            warnings=warnings,
        )
        _complete_job(deps, result)
        return result

    if deps.artifact_store is None:
        result = _failure(
            command,
            status="failed_non_retryable",
            error_code="artifact_store_not_configured",
            error_message="publish=true requires an artifact store.",
        )
        _complete_job(deps, result)
        return result

    pre_publish_result = RefreshResult(
        job_id=command.job_id,
        command_id=command.command_id,
        source_family=command.source_family,
        status="completed",
        row_count=summary.row_count,
        country_count=summary.country_count,
        metric_count=summary.metric_count,
        year_min=summary.year_min,
        year_max=summary.year_max,
        warnings=warnings,
    )
    artifact = deps.artifact_store.publish_package(
        command=command,
        dataframe=dataframe,
        validation_report=getattr(processing_result, "validation_report", None),
        diff_report=diff_report,
        result_payload=pre_publish_result,
    )
    _update_status(deps, command.job_id, "artifact_published")

    result = RefreshResult(
        job_id=command.job_id,
        command_id=command.command_id,
        source_family=command.source_family,
        status="completed",
        dataset_version=str(artifact.dataset_version) or None,
        artifact_uri=str(artifact.artifact_uri) or None,
        validation_report_uri=_path_to_uri(artifact.validation_report_path),
        diff_report_uri=_path_to_uri(artifact.diff_report_json_path),
        row_count=summary.row_count,
        country_count=summary.country_count,
        metric_count=summary.metric_count,
        year_min=summary.year_min,
        year_max=summary.year_max,
        warnings=warnings,
    )

    if deps.dataset_registry is not None:
        deps.dataset_registry.register_dataset_version(
            command=command,
            artifact=artifact,
            result=result,
        )

    _complete_job(deps, result)
    return result


def _processing_failure(command: RefreshCommand, processing_result: Any) -> RefreshResult:
    validation_report = getattr(processing_result, "validation_report", None)
    errors = list(getattr(validation_report, "error_messages", []) or [])
    error_message = (
        getattr(processing_result, "error", None)
        or "; ".join(errors)
        or "processing failed"
    )
    return _failure(
        command,
        status="failed_non_retryable",
        error_code="processing_failed",
        error_message=error_message,
    )


def _failure(
    command: RefreshCommand,
    *,
    status: str,
    error_code: str,
    error_message: str,
) -> RefreshResult:
    return RefreshResult(
        job_id=command.job_id,
        command_id=command.command_id,
        source_family=command.source_family,
        status=status,  # type: ignore[arg-type]
        error_code=error_code,
        error_message=error_message,
    )


def _mark_running(deps: RunnerDependencies, job_id: str) -> None:
    if deps.job_store is not None:
        deps.job_store.mark_running(job_id)


def _update_status(deps: RunnerDependencies, job_id: str, status: JobStatus) -> None:
    if deps.job_store is not None:
        deps.job_store.update_status(job_id, status)


def _complete_job(deps: RunnerDependencies, result: RefreshResult) -> None:
    if deps.job_store is not None:
        deps.job_store.complete_job(result)


def _collect_warnings(processing_result: Any) -> list[str]:
    warnings = [str(item) for item in (getattr(processing_result, "warnings", []) or [])]
    validation_report = getattr(processing_result, "validation_report", None)
    warnings.extend(
        str(item) for item in (getattr(validation_report, "warning_messages", []) or [])
    )
    return warnings


def _path_to_uri(path: Any) -> str | None:
    if path is None:
        return None
    resolved = Path(path)
    return resolved.as_uri() if resolved.is_absolute() else resolved.resolve().as_uri()
