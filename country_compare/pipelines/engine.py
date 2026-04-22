from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

import pandas as pd

from country_compare.data.contract import ALL_COLUMNS, PRIMARY_KEY_COLUMNS
from country_compare.data.ingestion.registry import resolve_source_adapter
from country_compare.pipelines.acquisition.directory import DirectoryRawAcquirer
from country_compare.pipelines.audit import write_audit_artifacts
from country_compare.pipelines.errors import AdapterExecutionError, CanonicalValidationError, PipelineError
from country_compare.pipelines.models import (
    AdapterResult,
    AuditReport,
    MergeReport,
    ProcessingRequest,
    ProcessingResult,
    PublicationReport,
    RejectedRow,
    RowIssue,
    RunMetadata,
    SourceProcessingResult,
    ValidationReport,
)
from country_compare.pipelines.publish import publish_dataframe


class PipelineEngine:
    def __init__(self, *, acquirer: DirectoryRawAcquirer | None = None) -> None:
        self.acquirer = acquirer or DirectoryRawAcquirer()

    def run(self, request: ProcessingRequest) -> ProcessingResult:
        started_at = datetime.now(tz=timezone.utc)
        run_metadata = RunMetadata(run_id=uuid4().hex, started_at=started_at, source_count=sum(1 for s in request.sources if s.enabled))
        source_results: list[SourceProcessingResult] = []
        warnings: list[str] = []
        run_error: str | None = None
        validation_report: ValidationReport | None = None
        publication_report: PublicationReport | None = None
        merge_report: MergeReport | None = None
        metric_dataset = None
        canonical_dataframe: pd.DataFrame | None = None
        try:
            for source_spec in request.sources:
                if not source_spec.enabled:
                    continue
                source_result = self._process_source(source_spec, request=request)
                source_results.append(source_result)
                warnings.extend(source_result.warnings)
                if not source_result.ok and source_result.error:
                    warnings.append(f"source '{source_spec.source_id}' failed: {source_result.error}")
                if not source_result.ok and request.stop_on_source_error:
                    raise PipelineError(source_result.error or 'source failure')
            successful = [result for result in source_results if result.ok and result.dataframe is not None]
            if not successful:
                raise PipelineError('no valid canonical outputs were produced by the pipeline')
            merge_report, merged = self._merge_source_results(successful)
            if not merge_report.ok or merged is None:
                message = merge_report.error or 'merge failed'
                validation_report = ValidationReport(ok=False, error_messages=[message], issues=[RowIssue(severity='error', code='merge_conflict', message=message, action='run_failed', stage='merge')], source_issue_count=sum(item.issue_count for item in source_results), rejected_row_count=sum(item.rejected_row_count for item in source_results), merge_checked=True, merge_conflict_count=merge_report.duplicate_key_conflict_count)
                raise CanonicalValidationError(message)
            validation_report, canonical_dataframe, metric_dataset = self._validate_merged_dataframe(merged, request=request, source_results=source_results, merge_report=merge_report)
            if not validation_report.ok:
                raise CanonicalValidationError('; '.join(validation_report.error_messages) or 'validation failed')
            if request.publish:
                publication_report = publish_dataframe(canonical_dataframe, store=request.store, write_metric_dataset=request.write_metric_dataset)
            else:
                publication_report = PublicationReport(attempted=False, ok=True, row_count=int(len(canonical_dataframe.index)), wrote_metric_dataset=request.write_metric_dataset)
        except Exception as exc:
            run_error = str(exc)
        if merge_report is None:
            merge_report = MergeReport(attempted=False, ok=False if run_error else True)
        if validation_report is None:
            validation_report = ValidationReport(ok=False, error_messages=[run_error or 'pipeline failed before validation'], source_issue_count=sum(item.issue_count for item in source_results), rejected_row_count=sum(item.rejected_row_count for item in source_results), merge_checked=merge_report.attempted, merge_conflict_count=merge_report.duplicate_key_conflict_count)
        if publication_report is None:
            publication_report = PublicationReport(attempted=request.publish, ok=False if request.publish else True, error=run_error if request.publish else None, wrote_metric_dataset=request.write_metric_dataset)
        finished_metadata = self._finalize_run_metadata(run_metadata, source_results=source_results, validation_report=validation_report, canonical_dataframe=canonical_dataframe if run_error is None else None, warnings=warnings, error=run_error)
        result = ProcessingResult(canonical_dataframe=canonical_dataframe if run_error is None else None, metric_dataset=metric_dataset if (run_error is None and request.write_metric_dataset) else None, source_results=tuple(source_results), validation_report=validation_report, publication_report=publication_report, merge_report=merge_report, run_metadata=finished_metadata, warnings=warnings, error=run_error)
        return self._attach_audit_report(result, request=request)

    def _process_source(self, source_spec: Any, *, request: ProcessingRequest) -> SourceProcessingResult:
        try:
            assets = tuple(self.acquirer.acquire(source_spec, raw_root=self._resolve_raw_root(request.raw_root)))
            adapter = resolve_source_adapter(source_spec.adapter_id)
            output = self._execute_adapter(adapter, assets, source_spec=source_spec)
            raw_row_count = output.raw_row_count
            if raw_row_count is None:
                raw_row_count = int(len(output.dataframe.index)) + len(output.rejected_rows)
            return SourceProcessingResult(source_id=source_spec.source_id, adapter_id=source_spec.adapter_id, ok=True, assets=assets, dataframe=output.dataframe, raw_row_count=int(raw_row_count), canonical_row_count=int(len(output.dataframe.index)), issues=output.issues, rejected_rows=output.rejected_rows, warnings=output.warnings, tags=tuple(getattr(source_spec, 'tags', ()) or ()), labels=dict(getattr(source_spec, 'labels', {}) or {}))
        except Exception as exc:
            return SourceProcessingResult(source_id=source_spec.source_id, adapter_id=source_spec.adapter_id, ok=False, error=str(exc), tags=tuple(getattr(source_spec, 'tags', ()) or ()), labels=dict(getattr(source_spec, 'labels', {}) or {}))

    @staticmethod
    def _resolve_raw_root(raw_root: str | Path | None) -> Path | None:
        return None if raw_root is None else Path(raw_root)

    @staticmethod
    def _execute_adapter(adapter: Any, assets: tuple[Any, ...], *, source_spec: Any) -> AdapterResult:
        try:
            if hasattr(adapter, 'process'):
                output = adapter.process(list(assets), source_spec=source_spec)
            elif len(assets) == 1 and hasattr(adapter, 'adapt'):
                output = adapter.adapt(assets[0], source_spec=source_spec)
            else:
                output = adapter.to_standardized_dataframe()
        except Exception as exc:
            raise AdapterExecutionError(str(exc)) from exc
        return _coerce_adapter_output(output)

    @staticmethod
    def _merge_source_results(source_results: list[SourceProcessingResult]) -> tuple[MergeReport, pd.DataFrame | None]:
        frames = [result.dataframe.copy(deep=True) for result in source_results if result.dataframe is not None]
        merged = pd.concat(frames, ignore_index=True)
        lineage_frames: list[pd.DataFrame] = []
        for result in source_results:
            if result.dataframe is None:
                continue
            lineage = result.dataframe.copy(deep=True)
            lineage['_source_id'] = result.source_id
            lineage['_adapter_id'] = result.adapter_id
            lineage_frames.append(lineage)
        lineage_df = pd.concat(lineage_frames, ignore_index=True)
        duplicate_mask = lineage_df.duplicated(subset=list(PRIMARY_KEY_COLUMNS), keep=False)
        if duplicate_mask.any():
            conflict_df = lineage_df.loc[duplicate_mask].copy()
            grouped = []
            for key_values, group in conflict_df.groupby(list(PRIMARY_KEY_COLUMNS), dropna=False, sort=True):
                if not isinstance(key_values, tuple):
                    key_values = (key_values,)
                key_dict = dict(zip(PRIMARY_KEY_COLUMNS, key_values))
                grouped.append({**key_dict, 'row_count': int(len(group.index)), 'source_ids': '|'.join(sorted(group['_source_id'].astype(str).unique().tolist())), 'adapter_ids': '|'.join(sorted(group['_adapter_id'].astype(str).unique().tolist()))})
            return MergeReport(attempted=True, ok=False, input_frame_count=len(frames), input_row_count=int(sum(len(frame.index) for frame in frames)), merged_row_count=int(len(merged.index)), duplicate_key_conflict_count=len(grouped), duplicate_key_row_count=int(len(conflict_df.index)), conflict_keys_preview=tuple(grouped[:10]), conflict_dataframe=conflict_df, error=f"duplicate canonical primary-key rows detected after merge: {tuple(grouped[:10])}"), None
        ordered = [column for column in ALL_COLUMNS if column in merged.columns]
        remaining = [column for column in merged.columns if column not in ordered]
        merged = merged.loc[:, [*ordered, *remaining]].copy(deep=True)
        return MergeReport(attempted=True, ok=True, input_frame_count=len(frames), input_row_count=int(sum(len(frame.index) for frame in frames)), merged_row_count=int(len(merged.index))), merged

    def _validate_merged_dataframe(self, dataframe: pd.DataFrame, *, request: ProcessingRequest, source_results: list[SourceProcessingResult], merge_report: MergeReport) -> tuple[ValidationReport, pd.DataFrame, Any | None]:
        errors: list[str] = []
        warnings: list[str] = []
        issues: list[RowIssue] = []
        config_checked = False
        validated_dataframe = dataframe.copy(deep=True)
        metric_dataset = None
        try:
            from country_compare.data import validation as validation_module
            prepared = validation_module.prepare_dataframe_for_storage(validated_dataframe)
            validated_dataframe = prepared.dataframe if hasattr(prepared, 'dataframe') else prepared
            metric_dataset = validation_module.dataframe_to_metric_dataset(validated_dataframe)
        except Exception as exc:
            errors.append(_normalize_validation_error_message(str(exc)))
            issues.append(RowIssue(severity='error', code='canonical_validation_failed', message=errors[-1], action='run_failed', stage='validation'))
        if not errors and request.validate_against_config:
            config_checked = True
            if request.metrics_config is None:
                warnings.append('Config validation was requested but no metrics_config was provided.')
            else:
                try:
                    from country_compare.config.validator import validate_metrics_against_dataframe
                    validate_metrics_against_dataframe(request.metrics_config, validated_dataframe)
                except Exception as exc:
                    errors.append(str(exc))
                    issues.append(RowIssue(severity='error', code='config_validation_failed', message=str(exc), action='run_failed', stage='validation'))
        report = ValidationReport(ok=not errors, error_messages=errors, warning_messages=warnings, issues=issues, validated_row_count=int(len(validated_dataframe.index)), config_checked=config_checked, source_issue_count=sum(item.issue_count for item in source_results), rejected_row_count=sum(item.rejected_row_count for item in source_results), merge_checked=merge_report.attempted, merge_conflict_count=merge_report.duplicate_key_conflict_count)
        return report, validated_dataframe, metric_dataset

    @staticmethod
    def _finalize_run_metadata(run_metadata: RunMetadata, *, source_results: list[SourceProcessingResult], validation_report: ValidationReport, canonical_dataframe: pd.DataFrame | None, warnings: list[str], error: str | None) -> RunMetadata:
        issue_count = sum(item.issue_count for item in source_results) + validation_report.issue_count
        warning_count = len(warnings) + len(validation_report.warning_messages)
        error_count = sum(item.error_count for item in source_results) + len(validation_report.error_messages)
        if error:
            error_count += 1
        return replace(run_metadata, finished_at=datetime.now(tz=timezone.utc), successful_source_count=sum(1 for item in source_results if item.ok), failed_source_count=sum(1 for item in source_results if not item.ok), canonical_row_count=0 if canonical_dataframe is None else int(len(canonical_dataframe.index)), rejected_row_count=sum(item.rejected_row_count for item in source_results), issue_count=issue_count, warning_count=warning_count, error_count=error_count)

    @staticmethod
    def _attach_audit_report(result: ProcessingResult, *, request: ProcessingRequest) -> ProcessingResult:
        if not request.write_audit_artifacts:
            return result
        artifact_paths = write_audit_artifacts(result, request=request)
        output_dir = request.output_dir
        if output_dir is None and artifact_paths:
            output_dir = Path(next(iter(artifact_paths.values()))).parent
        result.audit_report = AuditReport(written=True, output_dir=Path(output_dir) if output_dir is not None else None, artifact_paths=artifact_paths)
        return result


def _coerce_adapter_output(output: Any) -> AdapterResult:
    if isinstance(output, pd.DataFrame):
        return AdapterResult(dataframe=output.copy(deep=True), raw_row_count=int(len(output.index)))
    dataframe = getattr(output, 'dataframe', None)
    if not isinstance(dataframe, pd.DataFrame):
        raise AdapterExecutionError('adapter did not return a pandas DataFrame')
    issues = [issue if isinstance(issue, RowIssue) else RowIssue(**issue) for issue in (getattr(output, 'issues', []) or [])]
    rejected_rows = [rejected if isinstance(rejected, RejectedRow) else RejectedRow(**rejected) for rejected in (getattr(output, 'rejected_rows', []) or [])]
    warnings = [str(item) for item in getattr(output, 'warnings', []) or []]
    return AdapterResult(dataframe=dataframe.copy(deep=True), raw_row_count=getattr(output, 'raw_row_count', None), issues=issues, rejected_rows=rejected_rows, warnings=warnings)


def _normalize_validation_error_message(message: str) -> str:
    lowered = message.lower()
    if 'duplicate canonical primary-key rows detected after merge' in lowered:
        return message
    if 'duplicate rows found for primary key' in lowered or 'duplicate canonical primary-key rows' in lowered:
        return f'duplicate canonical primary-key rows detected after merge: {message}'
    return message


def run_processing_pipeline(request: ProcessingRequest) -> ProcessingResult:
    return PipelineEngine().run(request)
