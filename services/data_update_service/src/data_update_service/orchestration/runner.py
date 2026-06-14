from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

import pandas as pd

from data_update_service.orchestration.artifact_package import FilesystemArtifactStore
from data_update_service.orchestration.commands import RefreshCommand
from data_update_service.orchestration.diff import (
    DatasetDiffReport,
    generate_diff_report,
)
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
    ) -> Any:
        """Publish an immutable artifact package and return an ArtifactPackage-like object."""


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

    @classmethod
    def local_defaults(
        cls, settings: DataUpdateSettings | None = None
    ) -> RunnerDependencies:
        resolved = settings or DataUpdateSettings()
        return cls(
            pipeline_runner=CountryComparePipelineRunner(),
            diff_generator=DefaultDiffGenerator(),
            artifact_store=FilesystemArtifactStore(resolved.artifact_root),
            audit_root=resolved.audit_root,
        )


def run_refresh_job(
    command: RefreshCommand,
    dependencies: RunnerDependencies | None = None,
) -> RefreshResult:
    """Run a refresh job through the shared orchestration path.

    Milestone 1 keeps this deliberately small: it validates and runs the existing
    manifest pipeline, produces a diff skeleton, and optionally writes a local
    immutable artifact package. Kafka, job store, retries, and promotion will wrap
    this function later instead of changing the refresh behavior.
    """

    deps = dependencies or RunnerDependencies.local_defaults()
    audit_dir = deps.audit_root / command.source_family / command.job_id

    try:
        if not command.manifest.exists():
            return _failure(
                command,
                error_code="manifest_not_found",
                error_message=f"Manifest file not found: {command.manifest_path}",
            )

        processing_result = deps.pipeline_runner.run(command, audit_dir=audit_dir)
        if not bool(getattr(processing_result, "ok", False)):
            return _processing_failure(command, processing_result)

        dataframe = getattr(processing_result, "canonical_dataframe", None)
        if not isinstance(dataframe, pd.DataFrame):
            return _failure(
                command,
                error_code="missing_canonical_dataframe",
                error_message="Processing completed without a canonical dataframe.",
            )

        diff_report = deps.diff_generator.generate(dataframe)
        summary = diff_report.summary
        warnings = _collect_warnings(processing_result)

        if diff_report.no_changes:
            return RefreshResult(
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

        if command.dry_run or not command.publish:
            return RefreshResult(
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

        if deps.artifact_store is None:
            return _failure(
                command,
                error_code="artifact_store_not_configured",
                error_message="publish=true requires an artifact store.",
            )

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

        return RefreshResult(
            job_id=command.job_id,
            command_id=command.command_id,
            source_family=command.source_family,
            status="completed",
            dataset_version=str(getattr(artifact, "dataset_version", "")) or None,
            artifact_uri=str(getattr(artifact, "artifact_uri", "")) or None,
            validation_report_uri=_path_to_uri(
                getattr(artifact, "validation_report_path", None)
            ),
            diff_report_uri=_path_to_uri(
                getattr(artifact, "diff_report_json_path", None)
            ),
            row_count=summary.row_count,
            country_count=summary.country_count,
            metric_count=summary.metric_count,
            year_min=summary.year_min,
            year_max=summary.year_max,
            warnings=warnings,
        )
    except Exception as exc:  # pragma: no cover - defensive wrapper for CLI ergonomics
        return _failure(
            command,
            error_code=exc.__class__.__name__,
            error_message=str(exc),
        )


def _processing_failure(
    command: RefreshCommand, processing_result: Any
) -> RefreshResult:
    validation_report = getattr(processing_result, "validation_report", None)
    errors = list(getattr(validation_report, "error_messages", []) or [])
    error_message = (
        getattr(processing_result, "error", None)
        or "; ".join(errors)
        or "processing failed"
    )
    return _failure(
        command, error_code="processing_failed", error_message=error_message
    )


def _failure(
    command: RefreshCommand, *, error_code: str, error_message: str
) -> RefreshResult:
    return RefreshResult(
        job_id=command.job_id,
        command_id=command.command_id,
        source_family=command.source_family,
        status="failed_non_retryable",
        error_code=error_code,
        error_message=error_message,
    )


def _collect_warnings(processing_result: Any) -> list[str]:
    warnings = [
        str(item) for item in (getattr(processing_result, "warnings", []) or [])
    ]
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
