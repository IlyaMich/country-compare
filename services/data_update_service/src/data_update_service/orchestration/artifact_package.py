from __future__ import annotations

import hashlib
import json
import tempfile
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

    metrics_uri: str | None = None
    validation_report_uri: str | None = None
    diff_report_json_uri: str | None = None
    diff_report_markdown_uri: str | None = None
    command_uri: str | None = None
    result_uri: str | None = None
    manifest_uri: str | None = None
    catalog_uri: str | None = None
    source_audit_uri: str | None = None


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build_dataset_version(
    source_family: str, parquet_sha256: str, *, now: datetime | None = None
) -> str:
    timestamp = (
        (now or datetime.now(tz=UTC)).astimezone(UTC).strftime("%Y-%m-%dT%H-%M-%SZ")
    )
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

        dataset_version = build_dataset_version(
            command.source_family, parquet_sha256, now=now
        )
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
        diff_report_markdown_path.write_text(
            diff_report.as_markdown(), encoding="utf-8"
        )
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

        artifact_uri = version_dir.resolve().as_uri()

        return ArtifactPackage(
            dataset_version=dataset_version,
            artifact_dir=version_dir,
            artifact_uri=artifact_uri,
            parquet_sha256=parquet_sha256,
            metrics_path=final_metrics_path,
            validation_report_path=validation_report_path,
            diff_report_json_path=diff_report_json_path,
            diff_report_markdown_path=diff_report_markdown_path,
            command_path=command_path,
            result_path=result_path,
            metrics_uri=final_metrics_path.resolve().as_uri(),
            validation_report_uri=validation_report_path.resolve().as_uri(),
            diff_report_json_uri=diff_report_json_path.resolve().as_uri(),
            diff_report_markdown_uri=diff_report_markdown_path.resolve().as_uri(),
            command_uri=command_path.resolve().as_uri(),
            result_uri=result_path.resolve().as_uri(),
            manifest_uri=manifest_path.resolve().as_uri(),
            catalog_uri=catalog_path.resolve().as_uri(),
            source_audit_uri=source_audit_path.resolve().as_uri(),
        )


class S3ArtifactStore:
    """S3-compatible immutable artifact package publisher.

    This works with AWS S3, Cloudflare R2, Backblaze B2 S3-compatible API,
    and local MinIO by changing settings only.
    """

    def __init__(
        self,
        *,
        bucket: str,
        prefix: str = "datasets",
        endpoint_url: str | None = None,
        region_name: str | None = None,
        access_key_id: str | None = None,
        secret_access_key: str | None = None,
        local_staging_root: str | Path | None = None,
        client: Any | None = None,
    ) -> None:
        if not bucket.strip():
            raise ValueError("bucket is required for S3ArtifactStore")

        self.bucket = bucket
        self.prefix = prefix.strip("/")
        self.endpoint_url = endpoint_url
        self.region_name = region_name
        self.access_key_id = access_key_id
        self.secret_access_key = secret_access_key
        self.local_staging_root = (
            Path(local_staging_root)
            if local_staging_root is not None
            else Path(tempfile.mkdtemp(prefix="country-compare-data-update-s3-"))
        )
        self._client = client or self._build_client()

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
        local_store = FilesystemArtifactStore(self.local_staging_root)

        local_package = local_store.publish_package(
            command=command,
            dataframe=dataframe,
            validation_report=validation_report,
            diff_report=diff_report,
            result_payload=result_payload,
            now=now,
        )

        object_prefix = _join_object_key(
            self.prefix,
            command.source_family,
            "versions",
            local_package.dataset_version,
        )

        uploaded_uris: dict[str, str] = {}

        for path in sorted(local_package.artifact_dir.iterdir()):
            if not path.is_file():
                continue

            relative_name = path.name
            key = _join_object_key(object_prefix, relative_name)
            self._upload_file(path=path, key=key)
            uploaded_uris[relative_name] = _s3_uri(self.bucket, key)

        return ArtifactPackage(
            dataset_version=local_package.dataset_version,
            artifact_dir=local_package.artifact_dir,
            artifact_uri=_s3_uri(self.bucket, object_prefix) + "/",
            parquet_sha256=local_package.parquet_sha256,
            metrics_path=local_package.metrics_path,
            validation_report_path=local_package.validation_report_path,
            diff_report_json_path=local_package.diff_report_json_path,
            diff_report_markdown_path=local_package.diff_report_markdown_path,
            command_path=local_package.command_path,
            result_path=local_package.result_path,
            metrics_uri=uploaded_uris.get("metrics.parquet"),
            validation_report_uri=uploaded_uris.get("validation_report.json"),
            diff_report_json_uri=uploaded_uris.get("diff_report.json"),
            diff_report_markdown_uri=uploaded_uris.get("diff_report.md"),
            command_uri=uploaded_uris.get("refresh_command.json"),
            result_uri=uploaded_uris.get("refresh_result.json"),
            manifest_uri=uploaded_uris.get("metrics_manifest.json"),
            catalog_uri=uploaded_uris.get("catalog.json"),
            source_audit_uri=uploaded_uris.get("source_audit.json"),
        )

    def _build_client(self) -> Any:
        try:
            import boto3
        except ImportError as exc:  # pragma: no cover - exercised only without extra
            raise RuntimeError(
                "S3ArtifactStore requires boto3. Install with "
                "'services/data_update_service[s3]'."
            ) from exc

        kwargs: dict[str, Any] = {}

        if self.endpoint_url is not None:
            kwargs["endpoint_url"] = self.endpoint_url
        if self.region_name:
            kwargs["region_name"] = self.region_name
        if self.access_key_id is not None:
            kwargs["aws_access_key_id"] = self.access_key_id
        if self.secret_access_key is not None:
            kwargs["aws_secret_access_key"] = self.secret_access_key

        return boto3.client("s3", **kwargs)

    def _upload_file(self, *, path: Path, key: str) -> None:
        extra_args = {"ContentType": _content_type_for(path)}
        self._client.upload_file(
            Filename=str(path),
            Bucket=self.bucket,
            Key=key,
            ExtraArgs=extra_args,
        )


def _join_object_key(*parts: str) -> str:
    return "/".join(part.strip("/") for part in parts if part.strip("/"))


def _s3_uri(bucket: str, key: str) -> str:
    return f"s3://{bucket}/{key.strip('/')}"


def _content_type_for(path: Path) -> str:
    suffix = path.suffix.lower()

    if suffix == ".json":
        return "application/json"
    if suffix == ".md":
        return "text/markdown; charset=utf-8"
    if suffix == ".parquet":
        return "application/octet-stream"

    return "application/octet-stream"
