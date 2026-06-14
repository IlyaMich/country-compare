from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pandas as pd
from pydantic import BaseModel

from data_update_service.orchestration.commands import RefreshCommand
from data_update_service.orchestration.diff import DatasetDiffReport


@dataclass(frozen=True, slots=True)
class ArtifactPackage:
    dataset_version: str
    artifact_dir: Path
    artifact_uri: str
    parquet_sha256: str
    metrics_path: Path
    validation_report_path: Path
    diff_report_json_path: Path
    diff_report_markdown_path: Path
    command_path: Path
    result_path: Path


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build_dataset_version(
    source_family: str, parquet_sha256: str, *, now: datetime | None = None
) -> str:
    timestamp = (now or datetime.now(tz=UTC)).astimezone(UTC).strftime("%Y-%m-%dT%H-%M-%SZ")
    safe_source = source_family.strip().lower().replace("-", "_")
    return f"{safe_source}_{timestamp}_{parquet_sha256[:7]}"


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(_jsonable(payload), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _jsonable(value: Any) -> Any:
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json")
    if hasattr(value, "as_dict") and callable(value.as_dict):
        return value.as_dict()
    if hasattr(value, "__dataclass_fields__"):
        output: dict[str, Any] = {}
        for key in value.__dataclass_fields__:  # type: ignore[attr-defined]
            output[key] = _jsonable(getattr(value, key))
        return output
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_jsonable(item) for item in value]
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    return value


class FilesystemArtifactStore:
    """Local immutable artifact package writer used by Milestone 1."""

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)

    def publish_package(
        self,
        *,
        command: RefreshCommand,
        dataframe: pd.DataFrame,
        validation_report: Any,
        diff_report: DatasetDiffReport,
        result_payload: Any,
        now: datetime | None = None,
    ) -> ArtifactPackage:
        staging_dir = self.root / command.source_family / "_staging" / command.job_id
        staging_dir.mkdir(parents=True, exist_ok=True)

        metrics_path = staging_dir / "metrics.parquet"
        dataframe.to_parquet(metrics_path, index=False)
        parquet_sha256 = sha256_file(metrics_path)

        dataset_version = build_dataset_version(command.source_family, parquet_sha256, now=now)
        version_dir = self.root / command.source_family / "versions" / dataset_version
        if version_dir.exists():
            raise FileExistsError(f"artifact package already exists: {version_dir}")
        version_dir.mkdir(parents=True)

        final_metrics_path = version_dir / "metrics.parquet"
        metrics_path.replace(final_metrics_path)

        validation_report_path = version_dir / "validation_report.json"
        diff_report_json_path = version_dir / "diff_report.json"
        diff_report_markdown_path = version_dir / "diff_report.md"
        command_path = version_dir / "refresh_command.json"
        result_path = version_dir / "refresh_result.json"

        write_json(validation_report_path, validation_report)
        write_json(diff_report_json_path, diff_report)
        diff_report_markdown_path.write_text(diff_report.as_markdown(), encoding="utf-8")
        write_json(command_path, command)
        write_json(result_path, result_payload)

        manifest_path = version_dir / "metrics_manifest.json"
        catalog_path = version_dir / "catalog.json"
        source_audit_path = version_dir / "source_audit.json"
        write_json(
            manifest_path,
            {
                "dataset_version": dataset_version,
                "source_family": command.source_family,
                "parquet_sha256": parquet_sha256,
                "row_count": diff_report.summary.row_count,
                "country_count": diff_report.summary.country_count,
                "metric_count": diff_report.summary.metric_count,
                "year_min": diff_report.summary.year_min,
                "year_max": diff_report.summary.year_max,
                "created_at": (now or datetime.now(tz=UTC)).isoformat(),
            },
        )
        write_json(
            catalog_path,
            {
                "dataset_version": dataset_version,
                "files": [
                    "metrics.parquet",
                    "metrics_manifest.json",
                    "catalog.json",
                    "validation_report.json",
                    "diff_report.json",
                    "diff_report.md",
                    "source_audit.json",
                    "refresh_command.json",
                    "refresh_result.json",
                ],
            },
        )
        write_json(
            source_audit_path,
            {
                "job_id": command.job_id,
                "command_id": command.command_id,
                "source_family": command.source_family,
                "manifest_path": command.manifest_path,
                "note": "Detailed source audit artifacts remain in the pipeline audit directory.",
            },
        )

        try:
            staging_dir.rmdir()
            staging_dir.parent.rmdir()
        except OSError:
            pass

        return ArtifactPackage(
            dataset_version=dataset_version,
            artifact_dir=version_dir,
            artifact_uri=version_dir.resolve().as_uri(),
            parquet_sha256=parquet_sha256,
            metrics_path=final_metrics_path,
            validation_report_path=validation_report_path,
            diff_report_json_path=diff_report_json_path,
            diff_report_markdown_path=diff_report_markdown_path,
            command_path=command_path,
            result_path=result_path,
        )
