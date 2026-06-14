from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from threading import RLock
from typing import Any, Protocol

from data_update_service.orchestration.artifact_package import ArtifactPackage
from data_update_service.orchestration.commands import RefreshCommand
from data_update_service.orchestration.results import RefreshResult


@dataclass(frozen=True, slots=True)
class DatasetVersionRecord:
    dataset_version: str
    source_family: str
    artifact_uri: str
    parquet_sha256: str
    validation_report_uri: str | None
    diff_report_uri: str | None
    row_count: int
    country_count: int
    metric_count: int
    year_min: int | None
    year_max: int | None
    validation_status: str
    created_by_job_id: str
    created_at: datetime

    def as_dict(self) -> dict[str, Any]:
        return {
            "dataset_version": self.dataset_version,
            "source_family": self.source_family,
            "artifact_uri": self.artifact_uri,
            "parquet_sha256": self.parquet_sha256,
            "validation_report_uri": self.validation_report_uri,
            "diff_report_uri": self.diff_report_uri,
            "row_count": self.row_count,
            "country_count": self.country_count,
            "metric_count": self.metric_count,
            "year_min": self.year_min,
            "year_max": self.year_max,
            "validation_status": self.validation_status,
            "created_by_job_id": self.created_by_job_id,
            "created_at": self.created_at.isoformat(),
        }


class DatasetRegistry(Protocol):
    def register_dataset_version(
        self,
        *,
        command: RefreshCommand,
        artifact: ArtifactPackage,
        result: RefreshResult,
    ) -> DatasetVersionRecord:
        """Record a published immutable dataset version."""

    def get_dataset_version(self, dataset_version: str) -> DatasetVersionRecord | None:
        """Return dataset-version metadata if present."""

    def list_dataset_versions(
        self, *, source_family: str | None = None
    ) -> list[DatasetVersionRecord]:
        """List known dataset-version metadata records."""


class InMemoryDatasetRegistry:
    """Thread-safe in-memory dataset registry for tests."""

    def __init__(self) -> None:
        self._guard = RLock()
        self._records: dict[str, DatasetVersionRecord] = {}

    def register_dataset_version(
        self,
        *,
        command: RefreshCommand,
        artifact: ArtifactPackage,
        result: RefreshResult,
    ) -> DatasetVersionRecord:
        record = build_dataset_version_record(
            command=command, artifact=artifact, result=result
        )
        with self._guard:
            existing = self._records.get(record.dataset_version)
            if existing is not None:
                return existing
            self._records[record.dataset_version] = record
            return record

    def get_dataset_version(self, dataset_version: str) -> DatasetVersionRecord | None:
        with self._guard:
            return self._records.get(dataset_version)

    def list_dataset_versions(
        self, *, source_family: str | None = None
    ) -> list[DatasetVersionRecord]:
        with self._guard:
            records = list(self._records.values())
        if source_family is not None:
            records = [
                record for record in records if record.source_family == source_family
            ]
        return sorted(records, key=lambda item: item.created_at)


class FilesystemDatasetRegistry:
    """Small JSON registry used by the local filesystem artifact store."""

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)
        self._guard = RLock()

    def register_dataset_version(
        self,
        *,
        command: RefreshCommand,
        artifact: ArtifactPackage,
        result: RefreshResult,
    ) -> DatasetVersionRecord:
        record = build_dataset_version_record(
            command=command, artifact=artifact, result=result
        )
        with self._guard:
            records = self._read_records(command.source_family)
            if record.dataset_version not in records:
                records[record.dataset_version] = record
                self._write_records(command.source_family, records)
            return records[record.dataset_version]

    def get_dataset_version(self, dataset_version: str) -> DatasetVersionRecord | None:
        with self._guard:
            for source_dir in self.root.iterdir() if self.root.exists() else []:
                if not source_dir.is_dir():
                    continue
                records = self._read_records(source_dir.name)
                record = records.get(dataset_version)
                if record is not None:
                    return record
        return None

    def list_dataset_versions(
        self, *, source_family: str | None = None
    ) -> list[DatasetVersionRecord]:
        with self._guard:
            if source_family is not None:
                records = list(self._read_records(source_family).values())
            else:
                records = []
                for source_dir in self.root.iterdir() if self.root.exists() else []:
                    if source_dir.is_dir():
                        records.extend(self._read_records(source_dir.name).values())
        return sorted(records, key=lambda item: item.created_at)

    def _registry_path(self, source_family: str) -> Path:
        return self.root / source_family / "registry" / "dataset_versions.json"

    def _read_records(self, source_family: str) -> dict[str, DatasetVersionRecord]:
        path = self._registry_path(source_family)
        if not path.exists():
            return {}
        payload = json.loads(path.read_text(encoding="utf-8"))
        records = payload.get("dataset_versions", [])
        return {
            str(item["dataset_version"]): dataset_version_record_from_dict(item)
            for item in records
        }

    def _write_records(
        self, source_family: str, records: dict[str, DatasetVersionRecord]
    ) -> None:
        path = self._registry_path(source_family)
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "source_family": source_family,
            "dataset_versions": [record.as_dict() for record in records.values()],
        }
        path.write_text(
            json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )


def build_dataset_version_record(
    *,
    command: RefreshCommand,
    artifact: ArtifactPackage,
    result: RefreshResult,
) -> DatasetVersionRecord:
    return DatasetVersionRecord(
        dataset_version=artifact.dataset_version,
        source_family=command.source_family,
        artifact_uri=artifact.artifact_uri,
        parquet_sha256=artifact.parquet_sha256,
        validation_report_uri=result.validation_report_uri,
        diff_report_uri=result.diff_report_uri,
        row_count=result.row_count or 0,
        country_count=result.country_count or 0,
        metric_count=result.metric_count or 0,
        year_min=result.year_min,
        year_max=result.year_max,
        validation_status="passed" if result.ok else "failed",
        created_by_job_id=command.job_id,
        created_at=datetime.now(tz=UTC),
    )


def dataset_version_record_from_dict(payload: dict[str, Any]) -> DatasetVersionRecord:
    return DatasetVersionRecord(
        dataset_version=str(payload["dataset_version"]),
        source_family=str(payload["source_family"]),
        artifact_uri=str(payload["artifact_uri"]),
        parquet_sha256=str(payload["parquet_sha256"]),
        validation_report_uri=payload.get("validation_report_uri"),
        diff_report_uri=payload.get("diff_report_uri"),
        row_count=int(payload["row_count"]),
        country_count=int(payload["country_count"]),
        metric_count=int(payload["metric_count"]),
        year_min=(
            int(payload["year_min"]) if payload.get("year_min") is not None else None
        ),
        year_max=(
            int(payload["year_max"]) if payload.get("year_max") is not None else None
        ),
        validation_status=str(payload["validation_status"]),
        created_by_job_id=str(payload["created_by_job_id"]),
        created_at=datetime.fromisoformat(str(payload["created_at"])),
    )
