from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Literal, Mapping

import pandas as pd

Severity = Literal['warning', 'error']


def _normalize_tuple(values: Any) -> tuple[str, ...]:
    if values is None:
        return ()
    if isinstance(values, str):
        values = [values]
    output: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = str(value).strip()
        if not text or text in seen:
            continue
        output.append(text)
        seen.add(text)
    return tuple(output)


def _normalize_labels(values: Mapping[str, Any] | None) -> dict[str, str]:
    if values is None:
        return {}
    return {
        str(key).strip(): str(value).strip()
        for key, value in values.items()
        if str(key).strip()
    }


@dataclass(slots=True)
class SourceSpec:
    source_id: str
    adapter_id: str

    # local acquisition
    path: str | Path | None = None
    glob: str | None = None

    # remote acquisition
    remote_url: str | None = None
    download_filename: str | None = None

    # reader hints
    format_hint: str | None = None
    sheet_name: str | int | None = None
    read_options: dict[str, Any] = field(default_factory=dict)

    # source / dataset metadata
    source_name: str | None = None
    source_url: str | None = None
    dataset_version: str | None = None
    metric_id: str | None = None
    metric_name: str | None = None
    unit: str | None = None
    category: str | None = None
    higher_is_better: bool | str | int | None = None

    # column / adapter hints
    country_name_column: str | None = None
    country_code_column: str | None = None
    year_columns: list[str] | tuple[str, ...] | None = None
    mapping_overrides: dict[str, Any] = field(default_factory=dict)

    # pipeline flags / annotations
    enabled: bool = True
    metadata: dict[str, Any] = field(default_factory=dict)
    tags: tuple[str, ...] = ()
    labels: dict[str, str] = field(default_factory=dict)

    # World Bank-specific support
    expected_indicator_code: str | None = None
    filter_to_allowed_country_codes: bool = False
    allowed_country_codes: list[str] | tuple[str, ...] | None = None
    extra_allowed_country_codes: list[str] | tuple[str, ...] | None = None

    def __post_init__(self) -> None:
        self.source_id = str(self.source_id).strip()
        self.adapter_id = str(self.adapter_id).strip()

        if not self.source_id:
            raise ValueError("source_id must be a non-empty string")
        if not self.adapter_id:
            raise ValueError("adapter_id must be a non-empty string")

        self.path = Path(self.path) if self.path is not None else None
        self.glob = str(self.glob).strip() or None if self.glob is not None else None

        self.remote_url = str(self.remote_url).strip() or None if self.remote_url is not None else None
        self.download_filename = (
            str(self.download_filename).strip() or None
            if self.download_filename is not None
            else None
        )

        self.format_hint = str(self.format_hint).strip() or None if self.format_hint is not None else None

        self.source_name = str(self.source_name).strip() or None if self.source_name is not None else None
        self.source_url = str(self.source_url).strip() or None if self.source_url is not None else None
        self.dataset_version = (
            str(self.dataset_version).strip() or None
            if self.dataset_version is not None
            else None
        )
        self.metric_id = str(self.metric_id).strip() or None if self.metric_id is not None else None
        self.metric_name = str(self.metric_name).strip() or None if self.metric_name is not None else None
        self.unit = str(self.unit).strip() or None if self.unit is not None else None
        self.category = str(self.category).strip() or None if self.category is not None else None

        self.country_name_column = (
            str(self.country_name_column).strip() or None
            if self.country_name_column is not None
            else None
        )
        self.country_code_column = (
            str(self.country_code_column).strip() or None
            if self.country_code_column is not None
            else None
        )

        self.read_options = dict(self.read_options or {})
        if self.sheet_name is not None and "sheet_name" not in self.read_options:
            self.read_options["sheet_name"] = self.sheet_name

        self.mapping_overrides = dict(self.mapping_overrides or {})
        columns_mapping = self.mapping_overrides.get("columns")
        if columns_mapping is not None and not isinstance(columns_mapping, dict):
            raise ValueError("mapping_overrides['columns'] must be a mapping")

        self.metadata = dict(self.metadata or {})
        self.tags = _normalize_tuple(self.tags)
        self.labels = _normalize_labels(self.labels)

        if self.year_columns is not None:
            self.year_columns = [
                str(value).strip()
                for value in self.year_columns
                if str(value).strip()
            ]

        if self.expected_indicator_code is not None:
            self.expected_indicator_code = str(self.expected_indicator_code).strip() or None

        if self.allowed_country_codes is not None:
            self.allowed_country_codes = [
                str(value).strip().upper()
                for value in self.allowed_country_codes
                if str(value).strip()
            ]

        if self.extra_allowed_country_codes is not None:
            self.extra_allowed_country_codes = [
                str(value).strip().upper()
                for value in self.extra_allowed_country_codes
                if str(value).strip()
            ]

        if self.path is not None and self.glob is not None:
            raise ValueError("SourceSpec may set either path or glob, not both")

        if self.path is None and self.glob is None and self.remote_url is None:
            raise ValueError("SourceSpec requires one of path, glob, or remote_url")


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
class MergeReport:
    attempted: bool = False
    ok: bool = False
    input_frame_count: int = 0
    input_row_count: int = 0
    merged_row_count: int = 0
    duplicate_key_conflict_count: int = 0
    duplicate_key_row_count: int = 0
    conflict_keys_preview: tuple[dict[str, Any], ...] = ()
    conflict_dataframe: pd.DataFrame | None = None
    error: str | None = None


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
    merge_checked: bool = False
    merge_conflict_count: int = 0

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
    tags: tuple[str, ...] = ()
    labels: dict[str, str] = field(default_factory=dict)

    @property
    def rejected_row_count(self) -> int:
        return len(self.rejected_rows)

    @property
    def issue_count(self) -> int:
        return len(self.issues)

    @property
    def warning_count(self) -> int:
        return len(self.warnings) + sum(1 for issue in self.issues if issue.severity == 'warning')

    @property
    def error_count(self) -> int:
        return (1 if self.error else 0) + sum(1 for issue in self.issues if issue.severity == 'error')


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
    merge_report: MergeReport | None = None
    run_metadata: RunMetadata | None = None
    audit_report: AuditReport | None = None
    warnings: list[str] = field(default_factory=list)
    error: str | None = None

    @property
    def ok(self) -> bool:
        validation_ok = self.validation_report.ok if self.validation_report is not None else False
        publication_ok = True if self.publication_report is None or not self.publication_report.attempted else self.publication_report.ok
        merge_ok = True if self.merge_report is None else self.merge_report.ok
        return self.error is None and self.canonical_dataframe is not None and validation_ok and publication_ok and merge_ok
