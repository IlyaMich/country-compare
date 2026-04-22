from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Literal

import pandas as pd

Severity = Literal["warning", "error"]


@dataclass(slots=True)
class SourceSpec:
    source_id: str
    adapter_id: str
    path: str | Path | None = None
    glob: str | None = None
    format_hint: str | None = None
    sheet_name: str | int | None = None
    read_options: dict[str, Any] = field(default_factory=dict)

    source_name: str | None = None
    source_url: str | None = None
    dataset_version: str | None = None

    metric_id: str | None = None
    metric_name: str | None = None
    unit: str | None = None
    category: str | None = None
    higher_is_better: bool | str | int | None = None

    country_name_column: str | None = None
    country_code_column: str | None = None
    year_columns: list[str] | tuple[str, ...] | None = None

    mapping_overrides: dict[str, Any] = field(default_factory=dict)
    enabled: bool = True
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.source_id = str(self.source_id).strip()
        self.adapter_id = str(self.adapter_id).strip()
        if not self.source_id:
            raise ValueError("source_id must be a non-empty string")
        if not self.adapter_id:
            raise ValueError("adapter_id must be a non-empty string")
        if self.path is None and self.glob is None:
            raise ValueError("SourceSpec requires either 'path' or 'glob'")
        if self.path is not None:
            self.path = Path(self.path)
        if self.year_columns is not None:
            self.year_columns = [str(value) for value in self.year_columns]


@dataclass(slots=True)
class AcquiredAsset:
    source_id: str
    adapter_id: str
    local_path: Path
    file_format: str
    file_size: int
    checksum: str | None = None
    modified_at: datetime | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class RowIssue:
    severity: Severity
    code: str
    message: str
    source_id: str | None = None
    adapter_id: str | None = None
    row_identifier: str | None = None
    raw_row_number: int | None = None
    columns: tuple[str, ...] = ()
    action: str | None = None
    stage: str | None = None


@dataclass(slots=True)
class RejectedRow:
    reason: str
    source_id: str | None = None
    adapter_id: str | None = None
    row_identifier: str | None = None
    raw_row_number: int | None = None
    columns: tuple[str, ...] = ()
    payload: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class AdapterResult:
    dataframe: pd.DataFrame
    raw_row_count: int | None = None
    issues: list[RowIssue] = field(default_factory=list)
    rejected_rows: list[RejectedRow] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


@dataclass(slots=True)
class ValidationReport:
    ok: bool
    error_messages: list[str] = field(default_factory=list)
    warning_messages: list[str] = field(default_factory=list)
    issues: list[RowIssue] = field(default_factory=list)
    validated_row_count: int = 0
    config_checked: bool = False
    source_issue_count: int = 0
    rejected_row_count: int = 0

    @property
    def issue_count(self) -> int:
        return len(self.issues)


@dataclass(slots=True)
class PublicationReport:
    attempted: bool = False
    ok: bool = False
    row_count: int = 0
    target_backend: str | None = None
    target_path: str | None = None
    wrote_metric_dataset: bool = False
    error: str | None = None


@dataclass(slots=True)
class SourceProcessingResult:
    source_id: str
    adapter_id: str
    ok: bool
    assets: tuple[AcquiredAsset, ...] = ()
    dataframe: pd.DataFrame | None = None
    raw_row_count: int = 0
    canonical_row_count: int = 0
    issues: list[RowIssue] = field(default_factory=list)
    rejected_rows: list[RejectedRow] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    error: str | None = None

    @property
    def rejected_row_count(self) -> int:
        return len(self.rejected_rows)

    @property
    def issue_count(self) -> int:
        return len(self.issues)

    @property
    def warning_count(self) -> int:
        return len(self.warnings) + sum(1 for issue in self.issues if issue.severity == "warning")

    @property
    def error_count(self) -> int:
        return (1 if self.error else 0) + sum(1 for issue in self.issues if issue.severity == "error")

    @property
    def accepted_row_count(self) -> int:
        return self.canonical_row_count


@dataclass(slots=True)
class AuditReport:
    written: bool = False
    output_dir: Path | None = None
    artifact_paths: dict[str, str] = field(default_factory=dict)


@dataclass(slots=True)
class RunMetadata:
    run_id: str
    started_at: datetime
    finished_at: datetime | None = None
    source_count: int = 0
    successful_source_count: int = 0
    failed_source_count: int = 0
    canonical_row_count: int = 0
    rejected_row_count: int = 0
    issue_count: int = 0
    warning_count: int = 0
    error_count: int = 0

    @property
    def duration_seconds(self) -> float | None:
        if self.finished_at is None:
            return None
        return (self.finished_at - self.started_at).total_seconds()


@dataclass(slots=True)
class ProcessingRequest:
    sources: list[SourceSpec]
    raw_root: str | Path | None = None
    publish: bool = False
    write_metric_dataset: bool = False
    validate_against_config: bool = False
    metrics_config: Any | None = None
    store: Any | None = None
    stop_on_source_error: bool = False
    write_audit_artifacts: bool = False
    output_dir: str | Path | None = None
    canonical_preview_rows: int = 10

    def __post_init__(self) -> None:
        if self.raw_root is not None:
            self.raw_root = Path(self.raw_root)
        if self.output_dir is not None:
            self.output_dir = Path(self.output_dir)


@dataclass(slots=True)
class ProcessingResult:
    canonical_dataframe: pd.DataFrame | None = None
    metric_dataset: Any | None = None
    source_results: tuple[SourceProcessingResult, ...] = ()
    validation_report: ValidationReport | None = None
    publication_report: PublicationReport | None = None
    run_metadata: RunMetadata | None = None
    audit_report: AuditReport | None = None
    warnings: list[str] = field(default_factory=list)
    error: str | None = None

    @property
    def ok(self) -> bool:
        validation_ok = self.validation_report.ok if self.validation_report is not None else False
        publication_ok = (
            True
            if self.publication_report is None or not self.publication_report.attempted
            else self.publication_report.ok
        )
        return self.error is None and self.canonical_dataframe is not None and validation_ok and publication_ok
