from __future__ import annotations

import json
from dataclasses import asdict, is_dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd

from country_compare.pipelines.models import ProcessingRequest, ProcessingResult, RejectedRow, RowIssue


def write_audit_artifacts(
    result: ProcessingResult,
    *,
    request: ProcessingRequest,
) -> dict[str, str]:
    output_dir = _resolve_output_dir(result=result, request=request)
    output_dir.mkdir(parents=True, exist_ok=True)

    artifact_paths: dict[str, str] = {}

    run_summary_path = output_dir / "run_summary.json"
    run_summary_path.write_text(
        json.dumps(_build_run_summary(result), indent=2, sort_keys=True),
        encoding="utf-8",
    )
    artifact_paths["run_summary"] = str(run_summary_path)

    source_summary_path = output_dir / "source_summary.json"
    source_summary_path.write_text(
        json.dumps(_build_source_summary(result), indent=2, sort_keys=True),
        encoding="utf-8",
    )
    artifact_paths["source_summary"] = str(source_summary_path)

    publication_summary_path = output_dir / "publication_summary.json"
    publication_summary_path.write_text(
        json.dumps(_build_publication_summary(result), indent=2, sort_keys=True),
        encoding="utf-8",
    )
    artifact_paths["publication_summary"] = str(publication_summary_path)

    issues_path = output_dir / "row_issues.csv"
    _build_issue_dataframe(result).to_csv(issues_path, index=False)
    artifact_paths["row_issues"] = str(issues_path)

    rejected_path = output_dir / "rejected_rows.csv"
    _build_rejected_rows_dataframe(result).to_csv(rejected_path, index=False)
    artifact_paths["rejected_rows"] = str(rejected_path)

    if result.canonical_dataframe is not None:
        preview_rows = max(int(request.canonical_preview_rows), 0)
        preview_path = output_dir / "canonical_preview.csv"
        result.canonical_dataframe.head(preview_rows).to_csv(preview_path, index=False)
        artifact_paths["canonical_preview"] = str(preview_path)

    return artifact_paths


def _resolve_output_dir(*, result: ProcessingResult, request: ProcessingRequest) -> Path:
    if request.output_dir is not None:
        return Path(request.output_dir)

    run_id = result.run_metadata.run_id if result.run_metadata is not None else "processing_run"
    if request.raw_root is not None:
        return Path(request.raw_root) / "processing_audit" / run_id
    return Path.cwd() / "processing_audit" / run_id


def _build_run_summary(result: ProcessingResult) -> dict[str, Any]:
    run_metadata = result.run_metadata
    validation = result.validation_report
    publication = result.publication_report
    source_results = list(result.source_results)

    return {
        "ok": result.ok,
        "error": result.error,
        "warnings": list(result.warnings),
        "run_metadata": {
            "run_id": getattr(run_metadata, "run_id", None),
            "started_at": _json_value(getattr(run_metadata, "started_at", None)),
            "finished_at": _json_value(getattr(run_metadata, "finished_at", None)),
            "duration_seconds": getattr(run_metadata, "duration_seconds", None),
            "source_count": getattr(run_metadata, "source_count", 0),
            "successful_source_count": getattr(run_metadata, "successful_source_count", 0),
            "failed_source_count": getattr(run_metadata, "failed_source_count", 0),
            "canonical_row_count": getattr(run_metadata, "canonical_row_count", 0),
            "rejected_row_count": getattr(run_metadata, "rejected_row_count", 0),
            "issue_count": getattr(run_metadata, "issue_count", 0),
            "warning_count": getattr(run_metadata, "warning_count", 0),
            "error_count": getattr(run_metadata, "error_count", 0),
        },
        "source_counts": {
            "configured": len(source_results),
            "successful": sum(1 for item in source_results if item.ok),
            "failed": sum(1 for item in source_results if not item.ok),
        },
        "row_counts": {
            "canonical": 0 if result.canonical_dataframe is None else int(len(result.canonical_dataframe.index)),
            "rejected": sum(item.rejected_row_count for item in source_results),
        },
        "validation": {
            "ok": validation.ok if validation is not None else False,
            "validated_row_count": validation.validated_row_count if validation is not None else 0,
            "config_checked": validation.config_checked if validation is not None else False,
            "errors": [] if validation is None else list(validation.error_messages),
            "warnings": [] if validation is None else list(validation.warning_messages),
            "issue_count": 0 if validation is None else validation.issue_count,
        },
        "publication": _build_publication_summary(result),
    }


def _build_source_summary(result: ProcessingResult) -> list[dict[str, Any]]:
    summaries: list[dict[str, Any]] = []
    for source in result.source_results:
        summaries.append(
            {
                "source_id": source.source_id,
                "adapter_id": source.adapter_id,
                "ok": source.ok,
                "raw_row_count": source.raw_row_count,
                "canonical_row_count": source.canonical_row_count,
                "accepted_row_count": source.accepted_row_count,
                "rejected_row_count": source.rejected_row_count,
                "issue_count": source.issue_count,
                "warning_count": source.warning_count,
                "error_count": source.error_count,
                "warnings": list(source.warnings),
                "error": source.error,
                "assets": [
                    {
                        "local_path": str(asset.local_path),
                        "file_format": asset.file_format,
                        "file_size": asset.file_size,
                        "checksum": asset.checksum,
                        "modified_at": _json_value(asset.modified_at),
                    }
                    for asset in source.assets
                ],
            }
        )
    return summaries


def _build_publication_summary(result: ProcessingResult) -> dict[str, Any]:
    publication = result.publication_report
    if publication is None:
        return {
            "attempted": False,
            "ok": result.error is None,
        }
    return {
        "attempted": publication.attempted,
        "ok": publication.ok,
        "row_count": publication.row_count,
        "target_backend": publication.target_backend,
        "target_path": publication.target_path,
        "wrote_metric_dataset": publication.wrote_metric_dataset,
        "error": publication.error,
    }


def _build_issue_dataframe(result: ProcessingResult) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for source in result.source_results:
        for issue in source.issues:
            rows.append(_issue_to_row(issue, scope="source"))
    if result.validation_report is not None:
        for issue in result.validation_report.issues:
            rows.append(_issue_to_row(issue, scope="validation"))
    columns = [
        "scope",
        "severity",
        "code",
        "message",
        "source_id",
        "adapter_id",
        "row_identifier",
        "raw_row_number",
        "columns",
        "action",
        "stage",
    ]
    return pd.DataFrame(rows, columns=columns)


def _build_rejected_rows_dataframe(result: ProcessingResult) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for source in result.source_results:
        for rejected in source.rejected_rows:
            rows.append(_rejected_row_to_row(rejected))
    columns = [
        "source_id",
        "adapter_id",
        "row_identifier",
        "raw_row_number",
        "reason",
        "columns",
        "payload_json",
    ]
    return pd.DataFrame(rows, columns=columns)


def _issue_to_row(issue: RowIssue, *, scope: str) -> dict[str, Any]:
    return {
        "scope": scope,
        "severity": issue.severity,
        "code": issue.code,
        "message": issue.message,
        "source_id": issue.source_id,
        "adapter_id": issue.adapter_id,
        "row_identifier": issue.row_identifier,
        "raw_row_number": issue.raw_row_number,
        "columns": "|".join(issue.columns),
        "action": issue.action,
        "stage": issue.stage,
    }


def _rejected_row_to_row(rejected: RejectedRow) -> dict[str, Any]:
    return {
        "source_id": rejected.source_id,
        "adapter_id": rejected.adapter_id,
        "row_identifier": rejected.row_identifier,
        "raw_row_number": rejected.raw_row_number,
        "reason": rejected.reason,
        "columns": "|".join(rejected.columns),
        "payload_json": json.dumps(rejected.payload, sort_keys=True),
    }


def _json_value(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, Path):
        return str(value)
    if is_dataclass(value):
        return {key: _json_value(item) for key, item in asdict(value).items()}
    if isinstance(value, dict):
        return {str(key): _json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_value(item) for item in value]
    return value
