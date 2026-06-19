from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from threading import RLock
from typing import Any, Protocol

from data_update_service.orchestration.artifact_package import (
    ArtifactPackage,
    sha256_file,
)
from data_update_service.orchestration.commands import PromotionChannel, RefreshCommand
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
    manifest_sha256: str = ""
    catalog_sha256: str = ""

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
            "manifest_sha256": self.manifest_sha256,
            "catalog_sha256": self.catalog_sha256,
        }


@dataclass(frozen=True, slots=True)
class DatasetChannelRecord:
    channel: PromotionChannel
    source_family: str
    dataset_version: str
    artifact_uri: str
    parquet_sha256: str
    promoted_by: str
    promoted_at: datetime

    def as_dict(self) -> dict[str, Any]:
        return {
            "channel": self.channel,
            "source_family": self.source_family,
            "dataset_version": self.dataset_version,
            "artifact_uri": self.artifact_uri,
            "parquet_sha256": self.parquet_sha256,
            "promoted_by": self.promoted_by,
            "promoted_at": self.promoted_at.isoformat(),
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

    def promote_dataset_version(
        self,
        *,
        dataset_version: str,
        channel: PromotionChannel,
        promoted_by: str,
    ) -> DatasetChannelRecord:
        """Promote a registered dataset version to a channel."""

    def get_channel(
        self,
        *,
        source_family: str,
        channel: PromotionChannel,
    ) -> DatasetChannelRecord | None:
        """Return the current channel pointer if present."""

    def list_channels(
        self,
        *,
        source_family: str | None = None,
    ) -> list[DatasetChannelRecord]:
        """List channel pointers."""


class InMemoryDatasetRegistry:
    """Thread-safe in-memory dataset registry for tests."""

    def __init__(self) -> None:
        self._guard = RLock()
        self._records: dict[str, DatasetVersionRecord] = {}
        self._channels: dict[tuple[str, PromotionChannel], DatasetChannelRecord] = {}

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
                    record
                    for record in records
                    if record.source_family == source_family
                ]
            return sorted(records, key=lambda item: item.created_at)

    def promote_dataset_version(
        self,
        *,
        dataset_version: str,
        channel: PromotionChannel,
        promoted_by: str,
    ) -> DatasetChannelRecord:
        with self._guard:
            version = self._records.get(dataset_version)
            if version is None:
                raise KeyError(f"unknown dataset version: {dataset_version}")

            record = build_dataset_channel_record(
                version=version,
                channel=channel,
                promoted_by=promoted_by,
            )
            self._channels[(record.source_family, channel)] = record
            return record

    def get_channel(
        self,
        *,
        source_family: str,
        channel: PromotionChannel,
    ) -> DatasetChannelRecord | None:
        with self._guard:
            return self._channels.get((source_family, channel))

    def list_channels(
        self,
        *,
        source_family: str | None = None,
    ) -> list[DatasetChannelRecord]:
        with self._guard:
            channels = list(self._channels.values())
            if source_family is not None:
                channels = [
                    channel
                    for channel in channels
                    if channel.source_family == source_family
                ]
            return sorted(channels, key=lambda item: (item.source_family, item.channel))


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

    def promote_dataset_version(
        self,
        *,
        dataset_version: str,
        channel: PromotionChannel,
        promoted_by: str,
    ) -> DatasetChannelRecord:
        with self._guard:
            version = self.get_dataset_version(dataset_version)
            if version is None:
                raise KeyError(f"unknown dataset version: {dataset_version}")

            record = build_dataset_channel_record(
                version=version,
                channel=channel,
                promoted_by=promoted_by,
            )
            self._write_channel(record)
            return record

    def get_channel(
        self,
        *,
        source_family: str,
        channel: PromotionChannel,
    ) -> DatasetChannelRecord | None:
        with self._guard:
            path = self._channel_path(source_family, channel)
            if not path.exists():
                return None
            payload = json.loads(path.read_text(encoding="utf-8"))
            return dataset_channel_record_from_dict(payload)

    def list_channels(
        self,
        *,
        source_family: str | None = None,
    ) -> list[DatasetChannelRecord]:
        with self._guard:
            if source_family is not None:
                source_dirs = [self.root / source_family]
            else:
                source_dirs = [
                    path
                    for path in (self.root.iterdir() if self.root.exists() else [])
                    if path.is_dir()
                ]

            channels: list[DatasetChannelRecord] = []
            for source_dir in source_dirs:
                channels_dir = source_dir / "channels"
                if not channels_dir.exists():
                    continue
                for channel_path in channels_dir.glob("*.json"):
                    payload = json.loads(channel_path.read_text(encoding="utf-8"))
                    channels.append(dataset_channel_record_from_dict(payload))

            return sorted(channels, key=lambda item: (item.source_family, item.channel))

    def _registry_path(self, source_family: str) -> Path:
        return self.root / source_family / "registry" / "dataset_versions.json"

    def _channel_path(self, source_family: str, channel: PromotionChannel) -> Path:
        return self.root / source_family / "channels" / f"{channel}.json"

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
            json.dumps(payload, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

    def _write_channel(self, record: DatasetChannelRecord) -> None:
        path = self._channel_path(record.source_family, record.channel)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(record.as_dict(), indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
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
        manifest_sha256=_optional_artifact_file_sha256(
            artifact,
            "metrics_manifest.json",
        ),
        catalog_sha256=_optional_artifact_file_sha256(
            artifact,
            "catalog.json",
        ),
    )


def build_dataset_channel_record(
    *,
    version: DatasetVersionRecord,
    channel: PromotionChannel,
    promoted_by: str,
    promoted_at: datetime | None = None,
) -> DatasetChannelRecord:
    return DatasetChannelRecord(
        channel=channel,
        source_family=version.source_family,
        dataset_version=version.dataset_version,
        artifact_uri=version.artifact_uri,
        parquet_sha256=version.parquet_sha256,
        promoted_by=promoted_by,
        promoted_at=promoted_at or datetime.now(tz=UTC),
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
        manifest_sha256=str(payload.get("manifest_sha256") or ""),
        catalog_sha256=str(payload.get("catalog_sha256") or ""),
    )


def dataset_channel_record_from_dict(payload: dict[str, Any]) -> DatasetChannelRecord:
    return DatasetChannelRecord(
        channel=payload["channel"],
        source_family=str(payload["source_family"]),
        dataset_version=str(payload["dataset_version"]),
        artifact_uri=str(payload["artifact_uri"]),
        parquet_sha256=str(payload["parquet_sha256"]),
        promoted_by=str(payload["promoted_by"]),
        promoted_at=datetime.fromisoformat(str(payload["promoted_at"])),
    )


def _optional_artifact_file_sha256(artifact: ArtifactPackage, filename: str) -> str:
    artifact_dir = getattr(artifact, "artifact_dir", None)
    if artifact_dir is None:
        return ""

    path = Path(artifact_dir) / filename
    if not path.exists():
        return ""

    return sha256_file(path)
