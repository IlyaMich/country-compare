from __future__ import annotations

import json
from dataclasses import asdict, fields, is_dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd

from country_compare.pipelines.models import ProcessingRequest, ProcessingResult, RejectedRow, RowIssue


def _json_default(value: Any):
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, pd.Timestamp):
        return value.isoformat()
    if hasattr(value, 'item'):
        try:
            return value.item()
        except Exception:
            return str(value)
    if is_dataclass(value):
        return asdict(value)
    raise TypeError(f'Object of type {type(value).__name__} is not JSON serializable')


def _empty_dataframe_for_dataclass(dataclass_type: type[Any]) -> pd.DataFrame:
    return pd.DataFrame(columns=[field.name for field in fields(dataclass_type)])


def _write_csv(path: Path, rows: list[dict[str, Any]], *, dataclass_type: type[Any]) -> None:
    dataframe = pd.DataFrame(rows) if rows else _empty_dataframe_for_dataclass(dataclass_type)
    dataframe.to_csv(path, index=False)


def write_audit_artifacts(result: ProcessingResult, *, request: ProcessingRequest) -> dict[str, str]:
    output_dir = Path(request.output_dir or Path.cwd() / 'processing_audit')
    output_dir.mkdir(parents=True, exist_ok=True)
    artifact_paths: dict[str, str] = {}

    source_counts = {
        'total': len(result.source_results),
        'successful': sum(1 for item in result.source_results if item.ok),
        'failed': sum(1 for item in result.source_results if not item.ok),
    }
    row_counts = {
        'canonical': 0 if result.canonical_dataframe is None else int(len(result.canonical_dataframe.index)),
        'rejected': sum(item.rejected_row_count for item in result.source_results),
        'source_raw_total': sum(item.raw_row_count for item in result.source_results),
    }
    validation_summary = {
        'ok': None if result.validation_report is None else result.validation_report.ok,
        'errors': [] if result.validation_report is None else list(result.validation_report.error_messages),
        'warnings': [] if result.validation_report is None else list(result.validation_report.warning_messages),
        'validated_row_count': 0 if result.validation_report is None else result.validation_report.validated_row_count,
        'source_issue_count': 0 if result.validation_report is None else result.validation_report.source_issue_count,
        'rejected_row_count': 0 if result.validation_report is None else result.validation_report.rejected_row_count,
        'merge_checked': False if result.validation_report is None else result.validation_report.merge_checked,
        'merge_conflict_count': 0 if result.validation_report is None else result.validation_report.merge_conflict_count,
        'config_checked': False if result.validation_report is None else result.validation_report.config_checked,
    }
    publication_summary = {
        'attempted': False if result.publication_report is None else result.publication_report.attempted,
        'ok': None if result.publication_report is None else result.publication_report.ok,
        'row_count': 0 if result.publication_report is None else result.publication_report.row_count,
        'target_backend': None if result.publication_report is None else result.publication_report.target_backend,
        'target_path': None if result.publication_report is None else result.publication_report.target_path,
        'wrote_metric_dataset': False if result.publication_report is None else result.publication_report.wrote_metric_dataset,
        'error': None if result.publication_report is None else result.publication_report.error,
    }
    merge_summary = {
        'attempted': False if result.merge_report is None else result.merge_report.attempted,
        'ok': None if result.merge_report is None else result.merge_report.ok,
        'duplicate_key_conflict_count': 0 if result.merge_report is None else result.merge_report.duplicate_key_conflict_count,
        'duplicate_key_row_count': 0 if result.merge_report is None else result.merge_report.duplicate_key_row_count,
        'conflict_keys_preview': [] if result.merge_report is None else list(result.merge_report.conflict_keys_preview),
        'error': None if result.merge_report is None else result.merge_report.error,
    }

    run_summary = {
        'ok': result.ok,
        'error': result.error,
        'warnings': list(result.warnings),
        'source_counts': source_counts,
        'row_counts': row_counts,
        'validation': validation_summary,
        'publication': publication_summary,
        'merge': merge_summary,
        'run_metadata': None if result.run_metadata is None else asdict(result.run_metadata),
    }
    run_summary_path = output_dir / 'run_summary.json'
    run_summary_path.write_text(json.dumps(run_summary, indent=2, default=_json_default), encoding='utf-8')
    artifact_paths['run_summary'] = str(run_summary_path)

    source_summary = [
        {
            'source_id': item.source_id,
            'adapter_id': item.adapter_id,
            'ok': item.ok,
            'raw_row_count': item.raw_row_count,
            'canonical_row_count': item.canonical_row_count,
            'issue_count': item.issue_count,
            'rejected_row_count': item.rejected_row_count,
            'warning_count': item.warning_count,
            'error': item.error,
            'tags': list(item.tags),
            'labels': item.labels,
        }
        for item in result.source_results
    ]
    source_summary_path = output_dir / 'source_summary.json'
    source_summary_path.write_text(json.dumps(source_summary, indent=2), encoding='utf-8')
    artifact_paths['source_summary'] = str(source_summary_path)

    issues_rows: list[dict[str, Any]] = []
    rejected_rows: list[dict[str, Any]] = []
    for source_result in result.source_results:
        issues_rows.extend(asdict(issue) for issue in source_result.issues)
        rejected_rows.extend(asdict(rejected) for rejected in source_result.rejected_rows)
    if result.validation_report is not None:
        issues_rows.extend(asdict(issue) for issue in result.validation_report.issues)

    row_issues_path = output_dir / 'row_issues.csv'
    _write_csv(row_issues_path, issues_rows, dataclass_type=RowIssue)
    artifact_paths['row_issues'] = str(row_issues_path)

    rejected_rows_path = output_dir / 'rejected_rows.csv'
    _write_csv(rejected_rows_path, rejected_rows, dataclass_type=RejectedRow)
    artifact_paths['rejected_rows'] = str(rejected_rows_path)

    publication_summary_path = output_dir / 'publication_summary.json'
    publication_summary_path.write_text(json.dumps(publication_summary, indent=2, default=_json_default), encoding='utf-8')
    artifact_paths['publication_summary'] = str(publication_summary_path)

    if result.canonical_dataframe is not None:
        canonical_preview_path = output_dir / 'canonical_preview.csv'
        result.canonical_dataframe.head(max(1, int(request.canonical_preview_rows))).to_csv(canonical_preview_path, index=False)
        artifact_paths['canonical_preview'] = str(canonical_preview_path)

    if result.merge_report is not None and result.merge_report.conflict_dataframe is not None and not result.merge_report.conflict_dataframe.empty:
        conflict_path = output_dir / 'merge_conflicts.csv'
        result.merge_report.conflict_dataframe.to_csv(conflict_path, index=False)
        artifact_paths['merge_conflicts_csv'] = str(conflict_path)

    return artifact_paths
