from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

import pandas as pd

from country_compare.data.contract import (
    COUNTRY_CODE_COLUMN,
    DATASET_VERSION_COLUMN,
    METRIC_ID_COLUMN,
    YEAR_COLUMN,
)
from country_compare.data.validation import prepare_dataframe_for_read

DATASET_MANIFEST_FILENAME = "metrics_manifest.json"
DATASET_SCHEMA_VERSION = "country-compare-metric-dataset-v1"

IssueSeverity = Literal["error", "warning"]


@dataclass(frozen=True)
class ManifestValidationIssue:
    """Structured dataset manifest validation issue."""

    code: str
    message: str
    severity: IssueSeverity = "error"
    field: str | None = None
    expected: Any | None = None
    actual: Any | None = None


@dataclass(frozen=True)
class ManifestValidationResult:
    """Result from validating a processed dataset against its manifest."""

    valid: bool
    manifest_path: str | None = None
    dataset_path: str | None = None
    manifest: dict[str, Any] | None = None
    dataset_summary: dict[str, Any] = field(default_factory=dict)
    issues: tuple[ManifestValidationIssue, ...] = ()
    messages: tuple[str, ...] = ()

    @property
    def error_count(self) -> int:
        return sum(1 for issue in self.issues if issue.severity == "error")

    @property
    def warning_count(self) -> int:
        return sum(1 for issue in self.issues if issue.severity == "warning")

    def model_dump(self) -> dict[str, Any]:
        return _to_jsonable(asdict(self))


def _to_jsonable(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _to_jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_to_jsonable(item) for item in value]
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, (datetime,)):
        return value.isoformat()
    return value


def default_manifest_path_for_dataset(dataset_path: str | Path) -> Path:
    """Return the standard manifest path next to a processed dataset file."""

    return Path(dataset_path).with_name(DATASET_MANIFEST_FILENAME)


def compute_file_sha256(path: str | Path) -> str:
    """Compute a SHA-256 digest for a local dataset artifact."""

    resolved_path = Path(path)
    digest = hashlib.sha256()
    with resolved_path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build_manifest_from_dataframe_or_file(
    *,
    dataframe: pd.DataFrame | None = None,
    dataset_path: str | Path | None = None,
    dataset_file: str | None = None,
    dataset_version: str | None = None,
    created_at: datetime | str | None = None,
    schema_version: str = DATASET_SCHEMA_VERSION,
    source_manifest: str | None = None,
    pipeline_version: str | None = None,
    notes: str | None = None,
) -> dict[str, Any]:
    """Build a JSON-safe processed dataset manifest.

    A dataframe, a dataset file, or both may be provided. When only a file is
    provided the file is read as parquet and validated against the canonical
    dataset schema before summary fields are derived.
    """

    if dataframe is None and dataset_path is None:
        raise ValueError("Either dataframe or dataset_path must be provided.")

    resolved_dataset_path = Path(dataset_path) if dataset_path is not None else None
    working = _load_or_prepare_dataframe(dataframe, resolved_dataset_path)
    summary = _dataset_summary_from_dataframe(working)
    versions = _dataset_versions(working)

    if dataset_version is None:
        dataset_version = _resolve_dataset_version(versions)

    timestamp = _coerce_created_at(created_at)
    manifest: dict[str, Any] = {
        "dataset_version": dataset_version,
        "created_at": timestamp,
        "dataset_file": dataset_file
        or (resolved_dataset_path.name if resolved_dataset_path is not None else None),
        "sha256": (
            compute_file_sha256(resolved_dataset_path)
            if resolved_dataset_path is not None
            else None
        ),
        **summary,
        "schema_version": schema_version,
        "source_manifest": source_manifest,
        "pipeline_version": pipeline_version,
        "notes": notes,
    }
    if versions:
        manifest["dataset_versions"] = versions

    return {key: value for key, value in manifest.items() if value is not None}


def read_manifest(path: str | Path) -> dict[str, Any]:
    """Read a processed dataset manifest from JSON."""

    manifest_path = Path(path)
    raw = json.loads(manifest_path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError("Dataset manifest must be a JSON object.")
    return dict(raw)


def validate_manifest_against_dataset(
    *,
    manifest_path: str | Path,
    dataset_path: str | Path,
    dataframe: pd.DataFrame | None = None,
    expected_dataset_file: str | None = None,
) -> ManifestValidationResult:
    """Validate a processed dataset artifact against its manifest.

    Validation intentionally checks both file-level identity and dataframe-level
    summary consistency, so readiness can fail closed when a deployment mounts a
    stale manifest, a modified dataset, or an invalid canonical dataset.
    """

    resolved_manifest_path = Path(manifest_path)
    resolved_dataset_path = Path(dataset_path)
    issues: list[ManifestValidationIssue] = []
    manifest: dict[str, Any] | None = None
    summary: dict[str, Any] = {}

    if not resolved_manifest_path.exists():
        issues.append(
            ManifestValidationIssue(
                code="manifest_missing",
                message=f"Dataset manifest not found: {resolved_manifest_path}",
            )
        )

    if not resolved_dataset_path.exists():
        issues.append(
            ManifestValidationIssue(
                code="dataset_missing",
                message=f"Processed dataset not found: {resolved_dataset_path}",
            )
        )

    if issues:
        return _manifest_validation_result(
            valid=False,
            manifest_path=resolved_manifest_path,
            dataset_path=resolved_dataset_path,
            manifest=manifest,
            dataset_summary=summary,
            issues=issues,
        )

    try:
        manifest = read_manifest(resolved_manifest_path)
    except Exception as exc:
        issues.append(
            ManifestValidationIssue(
                code="manifest_invalid",
                message=f"Dataset manifest could not be read: {exc}",
            )
        )
        return _manifest_validation_result(
            valid=False,
            manifest_path=resolved_manifest_path,
            dataset_path=resolved_dataset_path,
            manifest=None,
            dataset_summary=summary,
            issues=issues,
        )

    actual_sha256 = compute_file_sha256(resolved_dataset_path)
    summary["sha256"] = actual_sha256
    _compare_manifest_field(
        issues,
        manifest,
        field="sha256",
        actual=actual_sha256,
        code="hash_mismatch",
        message="Dataset hash does not match manifest sha256.",
    )

    actual_dataset_file = expected_dataset_file or resolved_dataset_path.name
    expected_file = manifest.get("dataset_file")
    if expected_file is not None and str(expected_file) != actual_dataset_file:
        issues.append(
            ManifestValidationIssue(
                code="dataset_file_mismatch",
                message="Manifest dataset_file does not match the dataset filename.",
                field="dataset_file",
                expected=str(expected_file),
                actual=actual_dataset_file,
            )
        )

    try:
        working = _load_or_prepare_dataframe(dataframe, resolved_dataset_path)
    except Exception as exc:
        issues.append(
            ManifestValidationIssue(
                code="invalid_schema",
                message=f"Processed dataset schema validation failed: {exc}",
            )
        )
        return _manifest_validation_result(
            valid=False,
            manifest_path=resolved_manifest_path,
            dataset_path=resolved_dataset_path,
            manifest=manifest,
            dataset_summary=summary,
            issues=issues,
        )

    summary.update(_dataset_summary_from_dataframe(working))
    for field_name, code, label in (
        ("row_count", "row_count_mismatch", "row count"),
        ("country_count", "country_count_mismatch", "country count"),
        ("metric_count", "metric_count_mismatch", "metric count"),
        ("year_min", "year_min_mismatch", "minimum year"),
        ("year_max", "year_max_mismatch", "maximum year"),
    ):
        _compare_manifest_field(
            issues,
            manifest,
            field=field_name,
            actual=summary.get(field_name),
            code=code,
            message=f"Manifest {label} does not match the dataset.",
        )

    schema_version = manifest.get("schema_version")
    if schema_version != DATASET_SCHEMA_VERSION:
        issues.append(
            ManifestValidationIssue(
                code="schema_version_mismatch",
                message="Manifest schema_version is not the current canonical schema version.",
                field="schema_version",
                expected=DATASET_SCHEMA_VERSION,
                actual=schema_version,
            )
        )

    return _manifest_validation_result(
        valid=not any(issue.severity == "error" for issue in issues),
        manifest_path=resolved_manifest_path,
        dataset_path=resolved_dataset_path,
        manifest=manifest,
        dataset_summary=summary,
        issues=issues,
    )


def _manifest_validation_result(
    *,
    valid: bool,
    manifest_path: Path,
    dataset_path: Path,
    manifest: dict[str, Any] | None,
    dataset_summary: dict[str, Any],
    issues: list[ManifestValidationIssue],
) -> ManifestValidationResult:
    messages = tuple(issue.message for issue in issues if issue.message)
    return ManifestValidationResult(
        valid=valid,
        manifest_path=str(manifest_path),
        dataset_path=str(dataset_path),
        manifest=manifest,
        dataset_summary=dataset_summary,
        issues=tuple(issues),
        messages=messages,
    )


def _compare_manifest_field(
    issues: list[ManifestValidationIssue],
    manifest: dict[str, Any],
    *,
    field: str,
    actual: Any,
    code: str,
    message: str,
) -> None:
    if field not in manifest:
        issues.append(
            ManifestValidationIssue(
                code="manifest_field_missing",
                message=f"Manifest field '{field}' is required.",
                field=field,
                actual=None,
            )
        )
        return

    expected = manifest.get(field)
    if _normalize_comparable(expected) == _normalize_comparable(actual):
        return

    issues.append(
        ManifestValidationIssue(
            code=code,
            message=message,
            field=field,
            expected=expected,
            actual=actual,
        )
    )


def _normalize_comparable(value: Any) -> Any:
    if isinstance(value, float) and value.is_integer():
        return int(value)
    return value


def _load_or_prepare_dataframe(
    dataframe: pd.DataFrame | None,
    dataset_path: Path | None,
) -> pd.DataFrame:
    if dataframe is None:
        if dataset_path is None:
            raise ValueError("dataset_path is required when dataframe is not provided.")
        dataframe = pd.read_parquet(dataset_path)
    return prepare_dataframe_for_read(dataframe)


def _dataset_summary_from_dataframe(dataframe: pd.DataFrame) -> dict[str, Any]:
    year_values = pd.to_numeric(dataframe[YEAR_COLUMN], errors="coerce").dropna()
    return {
        "row_count": int(len(dataframe.index)),
        "country_count": int(dataframe[COUNTRY_CODE_COLUMN].dropna().nunique()),
        "metric_count": int(dataframe[METRIC_ID_COLUMN].dropna().nunique()),
        "year_min": int(year_values.min()) if not year_values.empty else None,
        "year_max": int(year_values.max()) if not year_values.empty else None,
    }


def _dataset_versions(dataframe: pd.DataFrame) -> list[str]:
    if DATASET_VERSION_COLUMN not in dataframe.columns:
        return []
    versions = dataframe[DATASET_VERSION_COLUMN].dropna().astype(str).map(str.strip)
    return sorted({value for value in versions.tolist() if value})


def _resolve_dataset_version(versions: list[str]) -> str | None:
    if len(versions) == 1:
        return versions[0]
    if len(versions) > 1:
        return ",".join(versions)
    return None


def _coerce_created_at(value: datetime | str | None) -> str:
    if value is None:
        return datetime.now(tz=UTC).replace(microsecond=0).isoformat()
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=UTC)
        return value.isoformat()
    return str(value)
