from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

import pandas as pd

from data_update_service.infrastructure.attempt_store import (
    AttemptRecord,
    AttemptStore,
    InMemoryAttemptStore,
)
from data_update_service.infrastructure.dataset_registry import (
    DatasetRegistry,
    FilesystemDatasetRegistry,
)
from data_update_service.infrastructure.job_store import (
    InMemoryJobStore,
    JobStatus,
    JobStore,
)
from data_update_service.infrastructure.locks import (
    InMemorySourceLockManager,
    SourceLockManager,
    SourceLockUnavailableError,
)
from data_update_service.infrastructure.postgres import (
    PostgresAttemptStore,
    PostgresDatasetRegistry,
    PostgresJobStore,
    PostgresSourceLockManager,
)
from data_update_service.orchestration.artifact_package import (
    ArtifactPackage,
    FilesystemArtifactStore,
)
from data_update_service.orchestration.commands import RefreshCommand
from data_update_service.orchestration.dataset_events import (
    DatasetEventPublisher,
    NoopDatasetEventPublisher,
    make_dataset_promotion_event,
    make_dataset_version_event,
)
from data_update_service.orchestration.diff import (
    DatasetDiffReport,
    generate_diff_report,
)
from data_update_service.orchestration.results import RefreshResult
from data_update_service.settings import DataUpdateSettings


class PipelineRunner(Protocol):
    def run(
        self,
        command: RefreshCommand,
        *,
        audit_dir: Path,
        raw_root: Path | None = None,
    ) -> Any:
        """Run the Country Compare processing path and return a ProcessingResult-like object."""


class SourceAcquirer(Protocol):
    def acquire(self, command: RefreshCommand) -> Any:
        """Acquire source files into a per-job snapshot and return an AcquisitionResult."""


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

    def run(
        self,
        command: RefreshCommand,
        *,
        audit_dir: Path,
        raw_root: Path | None = None,
    ) -> Any:
        from country_compare.config.loader import load_metrics_config
        from country_compare.paths import METRICS_CONFIG_PATH
        from country_compare.pipelines.runners import run_processing_manifest

        metrics_config_path = self.metrics_config_path or METRICS_CONFIG_PATH
        metrics_config = load_metrics_config(metrics_config_path)
        overrides: dict[str, Any] = {
            # `command.publish` means publish an immutable data-update artifact package.
            # It intentionally does not mutate the default `data/processed/metrics.parquet`.
            "publish": False,
            "write_metric_dataset": False,
            "validate_against_config": True,
            "metrics_config": metrics_config,
            "write_audit_artifacts": True,
            "output_dir": audit_dir,
        }
        if raw_root is not None:
            overrides["raw_root"] = raw_root
        return run_processing_manifest(command.manifest_path, **overrides)


class CountryCompareSourceAcquirer:
    """Adapter around Country Compare pipeline source snapshot acquisition."""

    def __init__(self, *, workspace_root: Path) -> None:
        self.workspace_root = workspace_root

    def acquire(self, command: RefreshCommand) -> Any:
        from country_compare.pipelines.acquisition.snapshot import (
            SourceSnapshotAcquirer,
        )

        acquirer = SourceSnapshotAcquirer(workspace_root=self.workspace_root)
        return acquirer.acquire_manifest_sources(
            job_id=command.job_id,
            source_family=command.source_family,
            manifest_path=command.manifest,
            acquisition_mode=command.acquisition_mode,
        )


class DefaultDiffGenerator:
    def generate(self, dataframe: pd.DataFrame) -> DatasetDiffReport:
        return generate_diff_report(dataframe)


@dataclass(frozen=True, slots=True)
class RunnerDependencies:
    pipeline_runner: PipelineRunner
    diff_generator: DiffGenerator
    source_acquirer: SourceAcquirer | None = None
    artifact_store: ArtifactStore | None = None
    audit_root: Path = Path("data/audit/data_update")
    job_store: JobStore | None = None
    attempt_store: AttemptStore | None = None
    source_locks: SourceLockManager | None = None
    dataset_registry: DatasetRegistry | None = None
    dataset_event_publisher: DatasetEventPublisher = field(
        default_factory=NoopDatasetEventPublisher
    )

    @classmethod
    def local_defaults(
        cls,
        settings: DataUpdateSettings | None = None,
    ) -> RunnerDependencies:
        resolved = settings or DataUpdateSettings.from_env()
        return cls(
            pipeline_runner=CountryComparePipelineRunner(),
            diff_generator=DefaultDiffGenerator(),
            source_acquirer=CountryCompareSourceAcquirer(
                workspace_root=resolved.workspace_root
            ),
            artifact_store=FilesystemArtifactStore(resolved.artifact_root),
            audit_root=resolved.audit_root,
            job_store=InMemoryJobStore(),
            source_locks=InMemorySourceLockManager(
                ttl_seconds=resolved.source_lock_ttl_seconds
            ),
            dataset_registry=FilesystemDatasetRegistry(resolved.artifact_root),
            attempt_store=InMemoryAttemptStore(),
        )

    @classmethod
    def postgres_defaults(
        cls,
        settings: DataUpdateSettings | None = None,
    ) -> RunnerDependencies:
        resolved = settings or DataUpdateSettings.from_env()
        initialize_schema = resolved.postgres_initialize_schema

        if resolved.database_url is None:
            raise ValueError(
                "DATA_UPDATE_DATABASE_URL is required when DATA_UPDATE_JOB_STORE=postgres"
            )

        return cls(
            pipeline_runner=CountryComparePipelineRunner(),
            diff_generator=DefaultDiffGenerator(),
            source_acquirer=CountryCompareSourceAcquirer(
                workspace_root=resolved.workspace_root
            ),
            artifact_store=FilesystemArtifactStore(resolved.artifact_root),
            audit_root=resolved.audit_root,
            job_store=PostgresJobStore(
                resolved.database_url,
                initialize_schema=initialize_schema,
            ),
            source_locks=PostgresSourceLockManager(
                resolved.database_url,
                ttl_seconds=resolved.source_lock_ttl_seconds,
                initialize_schema=initialize_schema,
            ),
            dataset_registry=PostgresDatasetRegistry(
                resolved.database_url,
                initialize_schema=initialize_schema,
            ),
            attempt_store=PostgresAttemptStore(
                resolved.database_url,
                initialize_schema=initialize_schema,
            ),
        )


def run_refresh_job(
    command: RefreshCommand,
    dependencies: RunnerDependencies | None = None,
) -> RefreshResult:
    """Run a refresh job through the shared orchestration path.

    The Kafka worker, CLI, and future private API should all call this function so
    refresh behavior stays consistent across entrypoints.
    """
    deps = dependencies or RunnerDependencies.local_defaults()

    if deps.job_store is not None:
        job_record = deps.job_store.create_or_get_job(command)

        if job_record.is_terminal:
            stored_result = deps.job_store.result_for_job(job_record.job_id)
            if stored_result is not None:
                return stored_result

    audit_dir = deps.audit_root / command.source_family / command.job_id
    attempt = _start_attempt(deps, command)
    result: RefreshResult | None = None

    try:
        try:
            if deps.source_locks is None:
                result = _execute_refresh(command, deps, audit_dir)
            else:
                with deps.source_locks.acquire(command.source_family, command.job_id):
                    result = _execute_refresh(command, deps, audit_dir)

        except SourceLockUnavailableError as exc:
            result = _failure(
                command,
                status="failed_retryable",
                error_code="source_lock_unavailable",
                error_message=str(exc),
            )
            _complete_job(deps, result)

        except (
            Exception
        ) as exc:  # pragma: no cover - defensive wrapper for CLI ergonomics
            result = _failure(
                command,
                status="failed_non_retryable",
                error_code=exc.__class__.__name__,
                error_message=str(exc),
            )
            _complete_job(deps, result)

        return result

    finally:
        if result is not None:
            _finish_attempt(deps, attempt, result)


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

    acquisition_result: Any | None = None
    raw_root: Path | None = None
    if deps.source_acquirer is not None:
        try:
            acquisition_result = deps.source_acquirer.acquire(command)
        except Exception as exc:
            result = _source_acquisition_failure(command, exc)
            _complete_job(deps, result)
            return result

        raw_dir = getattr(acquisition_result, "raw_dir", None)
        if raw_dir is not None:
            raw_root = Path(str(raw_dir))
        _update_status(deps, command.job_id, "source_acquired")

    processing_result = _run_pipeline(
        deps.pipeline_runner,
        command,
        audit_dir=audit_dir,
        raw_root=raw_root,
    )

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
    warnings = _collect_warnings(
        processing_result, acquisition_result=acquisition_result
    )

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

    if command.promote and deps.dataset_registry is None:
        result = _failure(
            command,
            status="failed_non_retryable",
            error_code="dataset_registry_not_configured",
            error_message="promote=true requires a dataset registry.",
        )
        _complete_job(deps, result)
        return result

    if command.promote and command.promotion_channel is None:
        result = _failure(
            command,
            status="failed_non_retryable",
            error_code="promotion_channel_required",
            error_message="promotion_channel is required when promote=true.",
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
        version_record = deps.dataset_registry.register_dataset_version(
            command=command,
            artifact=artifact,
            result=result,
        )
        deps.dataset_event_publisher.publish_dataset_version(
            make_dataset_version_event(
                command=command,
                record=version_record,
            )
        )

        if command.promote:
            if command.promotion_channel is None:
                raise ValueError("promotion_channel is required when promote=true")

            previous_channel = deps.dataset_registry.get_channel(
                source_family=command.source_family,
                channel=command.promotion_channel,
            )
            previous_dataset_version = (
                previous_channel.dataset_version
                if previous_channel is not None
                else None
            )

            channel_record = deps.dataset_registry.promote_dataset_version(
                dataset_version=artifact.dataset_version,
                channel=command.promotion_channel,
                promoted_by=command.requested_by,
            )
            deps.dataset_event_publisher.publish_dataset_promotion(
                make_dataset_promotion_event(
                    record=channel_record,
                    previous_dataset_version=previous_dataset_version,
                )
            )
            _update_status(deps, command.job_id, "promotion_completed")
    _complete_job(deps, result)
    return result


def _run_pipeline(
    pipeline_runner: PipelineRunner,
    command: RefreshCommand,
    *,
    audit_dir: Path,
    raw_root: Path | None,
) -> Any:
    if raw_root is None:
        return pipeline_runner.run(command, audit_dir=audit_dir)
    return pipeline_runner.run(command, audit_dir=audit_dir, raw_root=raw_root)


def _processing_failure(
    command: RefreshCommand,
    processing_result: Any,
) -> RefreshResult:
    return _failure(
        command,
        status="failed_non_retryable",
        error_code="processing_failed",
        error_message=_processing_error_message(processing_result),
    )


def _source_acquisition_failure(
    command: RefreshCommand, exc: Exception
) -> RefreshResult:
    if _is_retryable_source_acquisition_error(exc):
        return _failure(
            command,
            status="failed_retryable",
            error_code="source_acquisition_retryable",
            error_message=str(exc),
        )
    return _failure(
        command,
        status="failed_non_retryable",
        error_code="source_acquisition_failed",
        error_message=str(exc),
    )


def _is_retryable_source_acquisition_error(exc: Exception) -> bool:
    try:
        from country_compare.pipelines.acquisition.snapshot import (
            RetryableSourceSnapshotAcquisitionError,
        )
    except Exception:  # pragma: no cover - defensive if acquisition package unavailable
        return False
    return isinstance(exc, RetryableSourceSnapshotAcquisitionError)


def _processing_error_message(processing_result: Any) -> str:
    validation_report = getattr(processing_result, "validation_report", None)
    errors = list(getattr(validation_report, "error_messages", []) or [])
    return (
        str(getattr(processing_result, "error", "") or "")
        or "; ".join(str(error) for error in errors)
        or "processing failed"
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


def _start_attempt(
    deps: RunnerDependencies,
    command: RefreshCommand,
) -> AttemptRecord | None:
    if deps.attempt_store is None:
        return None

    return deps.attempt_store.start_attempt(command)


def _finish_attempt(
    deps: RunnerDependencies,
    attempt: AttemptRecord | None,
    result: RefreshResult,
) -> None:
    if deps.attempt_store is None or attempt is None:
        return

    deps.attempt_store.finish_attempt(
        attempt.attempt_id,
        status=result.status,
        error_code=result.error_code,
        error_message=result.error_message,
    )


def _collect_warnings(
    processing_result: Any,
    *,
    acquisition_result: Any | None = None,
) -> list[str]:
    warnings = [
        str(item) for item in (getattr(acquisition_result, "warnings", []) or [])
    ]
    warnings.extend(
        str(item) for item in (getattr(processing_result, "warnings", []) or [])
    )
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
