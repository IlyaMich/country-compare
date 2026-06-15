from __future__ import annotations

import hashlib
import shutil
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal, cast

from pydantic import BaseModel, ConfigDict, Field

from country_compare.pipelines.manifests import SourceManifest, load_source_manifest
from country_compare.pipelines.models import SourceSpec

AcquisitionMode = Literal["local", "remote", "auto"]


class SourceSnapshotAcquisitionError(RuntimeError):
    """Raised when a source snapshot cannot be created."""


class RetryableSourceSnapshotAcquisitionError(SourceSnapshotAcquisitionError):
    """Raised when source snapshot acquisition may succeed on retry."""


class NonRetryableSourceSnapshotAcquisitionError(SourceSnapshotAcquisitionError):
    """Raised when source snapshot acquisition should not be retried automatically."""


class AcquiredSourceAsset(BaseModel):
    """Audit metadata for one source file copied or acquired into a snapshot."""

    model_config = ConfigDict(extra="forbid")

    source_id: str = Field(min_length=1)
    metric_id: str | None = None
    provider: str = Field(min_length=1)
    indicator_code: str | None = None
    original_url: str | None = None
    raw_archive_path: str | None = None
    normalized_file_path: str = Field(min_length=1)
    metadata_paths: list[str] = Field(default_factory=list)
    sha256: str = Field(min_length=1)
    size_bytes: int = Field(ge=0)
    acquired_at: datetime
    cached: bool = False


class AcquisitionResult(BaseModel):
    """Result of creating a per-job source snapshot."""

    model_config = ConfigDict(extra="forbid")

    job_id: str = Field(min_length=1)
    source_family: str = Field(min_length=1)
    snapshot_dir: str = Field(min_length=1)
    raw_dir: str = Field(min_length=1)
    audit_path: str = Field(min_length=1)
    assets: list[AcquiredSourceAsset]
    warnings: list[str] = Field(default_factory=list)


class SourceSnapshotAcquirer:
    """Create a per-job source snapshot for a processing manifest.

    Local mode copies the manifest's resolved raw files into:

        {workspace_root}/jobs/{job_id}/source_snapshot/raw

    Remote mode currently supports World Bank indicator ZIP downloads. The
    downloaded data CSV is normalized into the same relative path used by the
    existing manifest, so the normal manifest pipeline can run with `raw_root`
    pointed at the snapshot raw directory.
    """

    def __init__(self, *, workspace_root: str | Path) -> None:
        self.workspace_root = Path(workspace_root)

    def acquire_manifest_sources(
        self,
        *,
        job_id: str,
        source_family: str,
        manifest_path: str | Path,
        acquisition_mode: AcquisitionMode = "local",
    ) -> AcquisitionResult:
        mode = _normalize_acquisition_mode(acquisition_mode)
        manifest = load_source_manifest(manifest_path)
        snapshot_dir = self.workspace_root / "jobs" / job_id / "source_snapshot"
        raw_dir = snapshot_dir / "raw"
        metadata_dir = snapshot_dir / "metadata"
        audit_path = snapshot_dir / "acquisition_audit.json"
        raw_dir.mkdir(parents=True, exist_ok=True)
        metadata_dir.mkdir(parents=True, exist_ok=True)

        if mode == "local":
            return self._acquire_local(
                job_id=job_id,
                source_family=source_family,
                manifest=manifest,
                manifest_path=Path(manifest_path),
                snapshot_dir=snapshot_dir,
                raw_dir=raw_dir,
                audit_path=audit_path,
            )

        if mode == "remote":
            return self._acquire_remote(
                job_id=job_id,
                source_family=source_family,
                manifest=manifest,
                snapshot_dir=snapshot_dir,
                raw_dir=raw_dir,
                metadata_dir=metadata_dir,
                audit_path=audit_path,
            )

        warnings: list[str] = []
        try:
            return self._acquire_local(
                job_id=job_id,
                source_family=source_family,
                manifest=manifest,
                manifest_path=Path(manifest_path),
                snapshot_dir=snapshot_dir,
                raw_dir=raw_dir,
                audit_path=audit_path,
            )
        except SourceSnapshotAcquisitionError as exc:
            warnings.append(f"local acquisition failed: {exc}")
            warnings.append(
                "persistent acquisition cache is not configured yet; falling back to remote"
            )
            return self._acquire_remote(
                job_id=job_id,
                source_family=source_family,
                manifest=manifest,
                snapshot_dir=snapshot_dir,
                raw_dir=raw_dir,
                metadata_dir=metadata_dir,
                audit_path=audit_path,
                warnings=warnings,
            )

    def _acquire_local(
        self,
        *,
        job_id: str,
        source_family: str,
        manifest: SourceManifest,
        manifest_path: Path,
        snapshot_dir: Path,
        raw_dir: Path,
        audit_path: Path,
    ) -> AcquisitionResult:
        raw_root = _resolve_manifest_raw_root(manifest.raw_root)
        assets: list[AcquiredSourceAsset] = []
        warnings: list[str] = []

        for source in manifest.sources:
            if not source.enabled:
                continue
            source_assets = self._copy_source_assets(
                source,
                source_family=source_family,
                raw_root=raw_root,
                raw_dir=raw_dir,
                snapshot_dir=snapshot_dir,
            )
            assets.extend(source_assets)

        if not assets:
            raise NonRetryableSourceSnapshotAcquisitionError(
                f"manifest produced no local source snapshot assets: {manifest_path}"
            )

        result = AcquisitionResult(
            job_id=job_id,
            source_family=source_family,
            snapshot_dir=str(snapshot_dir),
            raw_dir=str(raw_dir),
            audit_path=str(audit_path),
            assets=assets,
            warnings=warnings,
        )
        _write_audit(result, audit_path)
        return result

    def _copy_source_assets(
        self,
        source: SourceSpec,
        *,
        source_family: str,
        raw_root: Path,
        raw_dir: Path,
        snapshot_dir: Path,
    ) -> list[AcquiredSourceAsset]:
        if source.path is not None:
            source_relative_path = _safe_relative_manifest_path(source.path)
            source_path = Path(source.path)
            resolved_source = (
                source_path if source_path.is_absolute() else raw_root / source_path
            )
            if not resolved_source.exists() or not resolved_source.is_file():
                raise NonRetryableSourceSnapshotAcquisitionError(
                    f"source path does not exist for '{source.source_id}': {resolved_source}"
                )
            return [
                self._copy_one_source_file(
                    source,
                    source_family=source_family,
                    resolved_source=resolved_source,
                    destination_relative_path=source_relative_path,
                    raw_dir=raw_dir,
                    snapshot_dir=snapshot_dir,
                )
            ]

        if source.glob is None:
            raise NonRetryableSourceSnapshotAcquisitionError(
                f"source '{source.source_id}' does not define a local path or glob"
            )

        matches = sorted(path for path in raw_root.glob(source.glob) if path.is_file())
        if not matches:
            raise NonRetryableSourceSnapshotAcquisitionError(
                f"source glob matched no files for '{source.source_id}': "
                f"root={raw_root} pattern={source.glob}"
            )

        assets: list[AcquiredSourceAsset] = []
        for match in matches:
            destination_relative_path = _relative_to_or_name(
                match.resolve(), raw_root.resolve()
            )
            assets.append(
                self._copy_one_source_file(
                    source,
                    source_family=source_family,
                    resolved_source=match,
                    destination_relative_path=destination_relative_path,
                    raw_dir=raw_dir,
                    snapshot_dir=snapshot_dir,
                )
            )
        return assets

    @staticmethod
    def _copy_one_source_file(
        source: SourceSpec,
        *,
        source_family: str,
        resolved_source: Path,
        destination_relative_path: Path,
        raw_dir: Path,
        snapshot_dir: Path,
    ) -> AcquiredSourceAsset:
        destination = raw_dir / destination_relative_path
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(resolved_source, destination)
        stat = destination.stat()
        return AcquiredSourceAsset(
            source_id=source.source_id,
            metric_id=source.metric_id,
            provider=source_family,
            indicator_code=source.expected_indicator_code,
            original_url=source.remote_url,
            raw_archive_path=None,
            normalized_file_path=_path_relative_to(destination, snapshot_dir),
            metadata_paths=[],
            sha256=_sha256(destination),
            size_bytes=int(stat.st_size),
            acquired_at=datetime.now(tz=UTC),
            cached=False,
        )

    @staticmethod
    def _acquire_remote(
        *,
        job_id: str,
        source_family: str,
        manifest: SourceManifest,
        snapshot_dir: Path,
        raw_dir: Path,
        metadata_dir: Path,
        audit_path: Path,
        warnings: list[str] | None = None,
    ) -> AcquisitionResult:
        if source_family.strip().lower() != "world_bank":
            raise NonRetryableSourceSnapshotAcquisitionError(
                "remote source snapshot acquisition is only implemented for "
                f"source_family=world_bank; got {source_family!r}"
            )

        from country_compare.pipelines.acquisition.world_bank import (
            NonRetryableWorldBankAcquisitionError,
            RetryableWorldBankAcquisitionError,
            WorldBankAcquisitionError,
            WorldBankIndicatorSnapshotAcquirer,
        )

        try:
            world_bank_assets = (
                WorldBankIndicatorSnapshotAcquirer().acquire_manifest_sources(
                    manifest=manifest,
                    source_family=source_family,
                    snapshot_dir=snapshot_dir,
                    raw_dir=raw_dir,
                    metadata_dir=metadata_dir,
                )
            )
        except RetryableWorldBankAcquisitionError as exc:
            raise RetryableSourceSnapshotAcquisitionError(str(exc)) from exc
        except NonRetryableWorldBankAcquisitionError as exc:
            raise NonRetryableSourceSnapshotAcquisitionError(str(exc)) from exc
        except WorldBankAcquisitionError as exc:
            raise SourceSnapshotAcquisitionError(str(exc)) from exc

        result_warnings = list(warnings or [])
        result_warnings.extend(world_bank_assets.warnings)
        result = AcquisitionResult(
            job_id=job_id,
            source_family=source_family,
            snapshot_dir=str(snapshot_dir),
            raw_dir=str(raw_dir),
            audit_path=str(audit_path),
            assets=world_bank_assets.assets,
            warnings=result_warnings,
        )
        _write_audit(result, audit_path)
        return result


def _normalize_acquisition_mode(value: str) -> AcquisitionMode:
    normalized = value.strip().lower()
    if normalized in {"local", "remote", "auto"}:
        return cast(AcquisitionMode, normalized)
    raise SourceSnapshotAcquisitionError(
        f"unsupported acquisition_mode={value!r}; expected local, remote, or auto"
    )


def _resolve_manifest_raw_root(raw_root: str | Path | None) -> Path:
    return Path.cwd() if raw_root is None else Path(raw_root)


def _safe_relative_manifest_path(path: str | Path) -> Path:
    candidate = Path(path)
    if candidate.is_absolute():
        return Path(candidate.name)
    safe_parts = [part for part in candidate.parts if part not in {"", "."}]
    if not safe_parts or any(part == ".." for part in safe_parts):
        raise NonRetryableSourceSnapshotAcquisitionError(
            f"unsafe source path cannot be copied into source snapshot: {path}"
        )
    return Path(*safe_parts)


def _relative_to_or_name(path: Path, root: Path) -> Path:
    try:
        relative = path.relative_to(root)
    except ValueError:
        return Path(path.name)
    return _safe_relative_manifest_path(relative)


def _path_relative_to(path: Path, root: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return str(path)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _write_audit(result: AcquisitionResult, audit_path: Path) -> None:
    audit_path.parent.mkdir(parents=True, exist_ok=True)
    audit_path.write_text(result.model_dump_json(indent=2) + "\n", encoding="utf-8")
