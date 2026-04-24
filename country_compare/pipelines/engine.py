from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

import pandas as pd

from country_compare.data.contract import ALL_COLUMNS, PRIMARY_KEY_COLUMNS
from country_compare.data.ingestion.registry import resolve_source_adapter
from country_compare.pipelines.acquisition.base import RawAcquirer
from country_compare.pipelines.acquisition.remote import CompositeRawAcquirer
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
    def __init__(self, *, acquirer: RawAcquirer | None = None) -> None:
        self.acquirer = acquirer or CompositeRawAcquirer()

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
            tagged = result.dataframe.copy(deep=True)
            tagged['_source_id'] = result.source_id
            tagged['_adapter_id'] = result.adapter_id
            if result.tags:
                tagged['_source_tags'] = '|'.join(result.tags)
            if result.labels:
                for key, value in result.labels.items():
                    tagged[f'_source_label__{key}'] = value
            lineage_frames.append(tagged)
        merged_with_lineage = pd.concat(lineage_frames, ignore_index=True) if lineage_frames else pd.DataFrame()
        duplicate_mask = merged_with_lineage.duplicated(subset=list(PRIMARY_KEY_COLUMNS), keep=False) if not merged_with_lineage.empty else pd.Series(dtype=bool)
        if not merged_with_lineage.empty and duplicate_mask.any():
            conflicts = merged_with_lineage.loc[duplicate_mask].copy(deep=True)
            preview_columns = [column for column in [*PRIMARY_KEY_COLUMNS, '_source_id', '_adapter_id'] if column in conflicts.columns]
            preview_rows = conflicts.loc[:, preview_columns].drop_duplicates().head(20).to_dict(orient='records')
            message = 'duplicate canonical primary-key rows detected after merge: ' + str(preview_rows)
            return MergeReport(attempted=True, ok=False, input_frame_count=len(frames), input_row_count=sum(len(frame.index) for frame in frames), merged_row_count=int(len(merged.index)), duplicate_key_conflict_count=int(conflicts.loc[:, list(PRIMARY_KEY_COLUMNS)].drop_duplicates().shape[0]), duplicate_key_row_count=int(len(conflicts.index)), conflict_keys_preview=tuple(preview_rows), conflict_dataframe=conflicts, error=message), None
        ordered_columns = [column for column in ALL_COLUMNS if column in merged.columns]
        remaining_columns = [column for column in merged.columns if column not in ordered_columns]
        merged = merged.loc[:, [*ordered_columns, *remaining_columns]].copy(deep=True)
        return MergeReport(attempted=True, ok=True, input_frame_count=len(frames), input_row_count=sum(len(frame.index) for frame in frames), merged_row_count=int(len(merged.index))), merged

    def _validate_merged_dataframe(self, dataframe: pd.DataFrame, *, request: ProcessingRequest, source_results: list[SourceProcessingResult], merge_report: MergeReport) -> tuple[ValidationReport, pd.DataFrame, Any | None]:
        errors: list[str] = []
        warnings: list[str] = []
        issues: list[RowIssue] = []
        config_checked = False
        metric_dataset: Any | None = None
        try:
            validated_dataframe, metric_dataset = self._prepare_dataframe_for_storage(dataframe)
        except Exception as exc:
            message = _normalize_validation_error_message(str(exc))
            errors.append(message)
            issues.append(RowIssue(severity='error', code='canonical_validation_failed', message=message, action='run_failed', stage='validation'))
            validated_dataframe = dataframe.copy(deep=True)
        if not errors and request.validate_against_config:
            config_checked = True
            metrics_config = request.metrics_config
            if metrics_config is None:
                warnings.append('Config validation was requested but no metrics_config was provided.')
            else:
                try:
                    from country_compare.config.validator import validate_metrics_against_dataframe
                    validate_metrics_against_dataframe(metrics_config, validated_dataframe)
                except Exception as exc:
                    errors.append(str(exc))
                    issues.append(RowIssue(severity='error', code='config_validation_failed', message=str(exc), action='run_failed', stage='validation'))
        report = ValidationReport(ok=not errors, error_messages=errors, warning_messages=warnings, issues=issues, validated_row_count=int(len(validated_dataframe.index)), config_checked=config_checked, source_issue_count=sum(item.issue_count for item in source_results), rejected_row_count=sum(item.rejected_row_count for item in source_results), merge_checked=merge_report.attempted, merge_conflict_count=merge_report.duplicate_key_conflict_count)
        return report, validated_dataframe, metric_dataset

    @staticmethod
    def _prepare_dataframe_for_storage(dataframe: pd.DataFrame) -> tuple[pd.DataFrame, Any | None]:
        from country_compare.data import validation as validation_module
        candidate = dataframe.copy(deep=True)
        for function_name in ('prepare_dataframe_for_storage', 'canonicalize_and_validate_dataframe'):
            function = getattr(validation_module, function_name, None)
            if function is None:
                continue
            result = function(candidate.copy(deep=True))
            extracted = _extract_dataframe(result)
            if extracted is not None:
                candidate = extracted.copy(deep=True)
                break
        dataset = None
        dataframe_to_metric_dataset = getattr(validation_module, 'dataframe_to_metric_dataset', None)
        if callable(dataframe_to_metric_dataset):
            dataset = dataframe_to_metric_dataset(candidate)
        if dataset is None:
            _fallback_validate_dataframe(candidate)
        return candidate, dataset

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
        if output_dir is None:
            output_dir = Path(next(iter(artifact_paths.values()))).parent if artifact_paths else None
        result.audit_report = AuditReport(written=True, output_dir=Path(output_dir) if output_dir is not None else None, artifact_paths=artifact_paths)
        return result


def _coerce_adapter_output(output: Any) -> AdapterResult:
    if isinstance(output, pd.DataFrame):
        return AdapterResult(dataframe=output.copy(deep=True), raw_row_count=int(len(output.index)))
    dataframe = getattr(output, 'dataframe', None)
    if not isinstance(dataframe, pd.DataFrame):
        raise AdapterExecutionError('adapter did not return a pandas DataFrame')
    raw_row_count = getattr(output, 'raw_row_count', None)
    issues = _coerce_issues(getattr(output, 'issues', []))
    rejected_rows = _coerce_rejected_rows(getattr(output, 'rejected_rows', []))
    warnings = [str(item) for item in getattr(output, 'warnings', [])]
    return AdapterResult(dataframe=dataframe.copy(deep=True), raw_row_count=raw_row_count, issues=issues, rejected_rows=rejected_rows, warnings=warnings)


def _coerce_issues(values: Any) -> list[RowIssue]:
    issues: list[RowIssue] = []
    for value in values or []:
        if isinstance(value, RowIssue):
            issues.append(value)
            continue
        if isinstance(value, dict):
            issues.append(RowIssue(**value))
            continue
        raise AdapterExecutionError('adapter issues must contain RowIssue objects or mappings')
    return issues


def _coerce_rejected_rows(values: Any) -> list[RejectedRow]:
    rejected_rows: list[RejectedRow] = []
    for value in values or []:
        if isinstance(value, RejectedRow):
            rejected_rows.append(value)
            continue
        if isinstance(value, dict):
            rejected_rows.append(RejectedRow(**value))
            continue
        raise AdapterExecutionError('adapter rejected_rows must contain RejectedRow objects or mappings')
    return rejected_rows


def _extract_dataframe(result: Any) -> pd.DataFrame | None:
    if isinstance(result, pd.DataFrame):
        return result
    dataframe = getattr(result, 'dataframe', None)
    if isinstance(dataframe, pd.DataFrame):
        return dataframe
    return None


def _fallback_validate_dataframe(dataframe: pd.DataFrame) -> None:
    missing_required = [column for column in ALL_COLUMNS[:11] if column not in dataframe.columns]
    if missing_required:
        raise CanonicalValidationError(f'dataframe is missing required canonical columns: {missing_required}')
    duplicate_mask = dataframe.duplicated(subset=list(PRIMARY_KEY_COLUMNS), keep=False)
    if duplicate_mask.any():
        duplicates = dataframe.loc[duplicate_mask, list(PRIMARY_KEY_COLUMNS)]
        raise CanonicalValidationError('duplicate canonical primary-key rows detected: ' + str(duplicates.to_dict(orient='records')))
    for column in [
        'country_code', 'country_name', 'metric_id', 'metric_name', 'value', 'year', 'unit', 'source_name', 'source_url', 'higher_is_better', 'category'
    ]:
        if dataframe[column].isna().any():
            raise CanonicalValidationError(f"required column '{column}' contains missing values")
    years = pd.to_numeric(dataframe['year'], errors='raise')
    if ((years < 1900) | (years > 2100)).any():
        raise CanonicalValidationError('year values must be between 1900 and 2100')
    values = pd.to_numeric(dataframe['value'], errors='raise')
    if values.isna().any():
        raise CanonicalValidationError('value column contains invalid numeric values')
    country_codes = dataframe['country_code'].astype('string').str.upper()
    invalid_country_codes = country_codes[country_codes.str.len() != 3]
    if not invalid_country_codes.empty:
        raise CanonicalValidationError('country_code must contain ISO alpha-3 codes')


def _normalize_validation_error_message(message: str) -> str:
    lowered = message.lower()
    if 'duplicate canonical primary-key rows detected after merge' in lowered:
        return message
    if 'duplicate canonical primary-key rows' in lowered or 'duplicate rows found for primary key' in lowered or '[duplicates]' in lowered:
        return f'duplicate canonical primary-key rows detected after merge: {message}'
    return message


def run_processing_pipeline(request: ProcessingRequest) -> ProcessingResult:
    return PipelineEngine().run(request)