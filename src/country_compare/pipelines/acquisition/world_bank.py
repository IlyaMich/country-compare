from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Final
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen
from zipfile import BadZipFile, ZipFile, ZipInfo

from country_compare.pipelines.acquisition.archive import (
    UnsafeArchiveError,
    extract_zip_member,
    safe_zip_members,
    sha256_file,
)
from country_compare.pipelines.acquisition.snapshot import AcquiredSourceAsset
from country_compare.pipelines.manifests import SourceManifest
from country_compare.pipelines.models import SourceSpec

_DEFAULT_LANGUAGE: Final[str] = "en"
_DEFAULT_SOURCE_ID: Final[int] = 2
_DEFAULT_TIMEOUT_SECONDS: Final[int] = 60
_USER_AGENT: Final[str] = "country-compare-data-update/0.1"


class WorldBankAcquisitionError(RuntimeError):
    """Base error for World Bank source acquisition."""


class RetryableWorldBankAcquisitionError(WorldBankAcquisitionError):
    """Raised for transient World Bank acquisition failures."""


class NonRetryableWorldBankAcquisitionError(WorldBankAcquisitionError):
    """Raised for deterministic World Bank acquisition failures."""


@dataclass(frozen=True, slots=True)
class WorldBankAcquisitionPlan:
    language: str = _DEFAULT_LANGUAGE
    source_id: int = _DEFAULT_SOURCE_ID
    timeout_seconds: int = _DEFAULT_TIMEOUT_SECONDS
    max_download_attempts: int = 3
    retry_backoff_seconds: float = 1.0


@dataclass(slots=True)
class WorldBankSnapshotAssets:
    assets: list[AcquiredSourceAsset]
    warnings: list[str] = field(default_factory=list)


def build_world_bank_indicator_zip_url(
    indicator_code: str,
    *,
    language: str = _DEFAULT_LANGUAGE,
    source_id: int = _DEFAULT_SOURCE_ID,
) -> str:
    """Build the World Bank CSV ZIP download URL for one WDI indicator."""

    normalized = indicator_code.strip()
    if not normalized:
        raise NonRetryableWorldBankAcquisitionError("indicator_code must not be empty")

    encoded_indicator = quote(normalized, safe="")
    encoded_language = quote(language.strip() or _DEFAULT_LANGUAGE, safe="")

    return (
        f"https://api.worldbank.org/v2/{encoded_language}/country/all/indicator/"
        f"{encoded_indicator}?source={int(source_id)}&downloadformat=csv"
    )


class WorldBankIndicatorSnapshotAcquirer:
    """Download World Bank indicator ZIPs into a source snapshot.

    The existing manifests remain backward-compatible: each source keeps its
    current local `path`, and this acquirer normalizes the downloaded World Bank
    data CSV into that same relative path under the snapshot raw directory.
    """

    def __init__(self, *, plan: WorldBankAcquisitionPlan | None = None) -> None:
        self.plan = plan or WorldBankAcquisitionPlan()

    def acquire_manifest_sources(
        self,
        *,
        manifest: SourceManifest,
        source_family: str,
        snapshot_dir: Path,
        raw_dir: Path,
        metadata_dir: Path,
    ) -> WorldBankSnapshotAssets:
        archive_dir = snapshot_dir / "archives"
        archive_dir.mkdir(parents=True, exist_ok=True)
        metadata_dir.mkdir(parents=True, exist_ok=True)
        raw_dir.mkdir(parents=True, exist_ok=True)

        assets: list[AcquiredSourceAsset] = []
        warnings: list[str] = []

        for source in manifest.sources:
            if not source.enabled:
                continue

            assets.append(
                self._acquire_source(
                    source,
                    source_family=source_family,
                    archive_dir=archive_dir,
                    raw_dir=raw_dir,
                    metadata_dir=metadata_dir,
                    snapshot_dir=snapshot_dir,
                )
            )

        if not assets:
            raise NonRetryableWorldBankAcquisitionError(
                "World Bank manifest produced no enabled sources to acquire"
            )

        return WorldBankSnapshotAssets(assets=assets, warnings=warnings)

    def _acquire_source(
        self,
        source: SourceSpec,
        *,
        source_family: str,
        archive_dir: Path,
        raw_dir: Path,
        metadata_dir: Path,
        snapshot_dir: Path,
    ) -> AcquiredSourceAsset:
        indicator_code = (source.expected_indicator_code or "").strip()
        if not indicator_code:
            raise NonRetryableWorldBankAcquisitionError(
                f"source '{source.source_id}' is missing expected_indicator_code"
            )

        if source.path is None:
            raise NonRetryableWorldBankAcquisitionError(
                f"source '{source.source_id}' must define path for snapshot normalization"
            )

        original_url = build_world_bank_indicator_zip_url(
            indicator_code,
            language=self.plan.language,
            source_id=self.plan.source_id,
        )
        archive_path = archive_dir / f"{source.source_id}.zip"

        self._download_zip(original_url, archive_path, source_id=source.source_id)

        source_metadata_dir = metadata_dir / source.source_id
        normalized_path = raw_dir / _safe_relative_output_path(source.path)

        metadata_paths = self._extract_world_bank_zip(
            archive_path,
            source=source,
            indicator_code=indicator_code,
            normalized_path=normalized_path,
            metadata_dir=source_metadata_dir,
        )

        stat = normalized_path.stat()

        return AcquiredSourceAsset(
            source_id=source.source_id,
            metric_id=source.metric_id,
            provider=source_family,
            indicator_code=indicator_code,
            original_url=original_url,
            raw_archive_path=_path_relative_to(archive_path, snapshot_dir),
            normalized_file_path=_path_relative_to(normalized_path, snapshot_dir),
            metadata_paths=[
                _path_relative_to(path, snapshot_dir) for path in metadata_paths
            ],
            sha256=sha256_file(normalized_path),
            size_bytes=int(stat.st_size),
            acquired_at=datetime.now(tz=UTC),
            cached=False,
        )

    def _download_zip(self, url: str, destination: Path, *, source_id: str) -> None:
        attempt_count = max(1, int(self.plan.max_download_attempts))
        backoff_seconds = max(0.0, float(self.plan.retry_backoff_seconds))

        last_error: RetryableWorldBankAcquisitionError | None = None

        for attempt_number in range(1, attempt_count + 1):
            try:
                self._download_zip_once(url, destination, source_id=source_id)
                return
            except RetryableWorldBankAcquisitionError as exc:
                last_error = exc
                if attempt_number >= attempt_count:
                    raise RetryableWorldBankAcquisitionError(
                        f"{exc} after {attempt_count} download attempts"
                    ) from exc

                if backoff_seconds > 0:
                    time.sleep(backoff_seconds * attempt_number)

        if last_error is not None:
            raise last_error

    def _download_zip_once(
        self, url: str, destination: Path, *, source_id: str
    ) -> None:
        destination.parent.mkdir(parents=True, exist_ok=True)
        request = Request(url, headers={"User-Agent": _USER_AGENT})

        try:
            with urlopen(request, timeout=self.plan.timeout_seconds) as response:
                status = getattr(response, "status", 200)
                if int(status) >= 400:
                    self._raise_for_http_status(int(status), url, source_id=source_id)

                with destination.open("wb") as handle:
                    while True:
                        chunk = response.read(1024 * 1024)
                        if not chunk:
                            break
                        handle.write(chunk)

        except HTTPError as exc:
            self._raise_for_http_status(exc.code, url, source_id=source_id)

        except (TimeoutError, URLError) as exc:
            raise RetryableWorldBankAcquisitionError(
                f"temporary failure downloading World Bank source '{source_id}': {url}"
            ) from exc

        except OSError as exc:
            raise RetryableWorldBankAcquisitionError(
                f"temporary filesystem/network failure downloading World Bank source "
                f"'{source_id}': {url}"
            ) from exc

    @staticmethod
    def _raise_for_http_status(status_code: int, url: str, *, source_id: str) -> None:
        if status_code == 429 or 500 <= status_code <= 599:
            raise RetryableWorldBankAcquisitionError(
                f"World Bank returned retryable HTTP {status_code} for "
                f"source '{source_id}': {url}"
            )

        raise NonRetryableWorldBankAcquisitionError(
            f"World Bank returned HTTP {status_code} for source '{source_id}': {url}"
        )

    def _extract_world_bank_zip(
        self,
        archive_path: Path,
        *,
        source: SourceSpec,
        indicator_code: str,
        normalized_path: Path,
        metadata_dir: Path,
    ) -> list[Path]:
        try:
            with ZipFile(archive_path) as zip_file:
                members = safe_zip_members(zip_file)
                data_member = _select_indicator_data_csv(members)

                extract_zip_member(zip_file, data_member, normalized_path)

                _validate_indicator_code(
                    normalized_path,
                    indicator_code,
                    source_id=source.source_id,
                )

                return _extract_metadata_csvs(
                    zip_file,
                    members,
                    metadata_dir=metadata_dir,
                    source_id=source.source_id,
                )

        except BadZipFile as exc:
            raise NonRetryableWorldBankAcquisitionError(
                f"World Bank source '{source.source_id}' did not return a valid ZIP archive"
            ) from exc

        except UnsafeArchiveError as exc:
            raise NonRetryableWorldBankAcquisitionError(
                f"World Bank source '{source.source_id}' ZIP archive is unsafe: {exc}"
            ) from exc


def _select_indicator_data_csv(members: list[ZipInfo]) -> ZipInfo:
    csv_members = [
        member for member in members if member.filename.lower().endswith(".csv")
    ]

    data_members = [
        member
        for member in csv_members
        if Path(member.filename).name.lower().startswith("api_")
    ]
    if len(data_members) == 1:
        return data_members[0]

    non_metadata = [
        member
        for member in csv_members
        if not Path(member.filename).name.lower().startswith("metadata_")
    ]
    if len(non_metadata) == 1:
        return non_metadata[0]

    names = ", ".join(Path(member.filename).name for member in csv_members)
    raise NonRetryableWorldBankAcquisitionError(
        "could not identify exactly one World Bank data CSV in archive; "
        f"csv_members=[{names}]"
    )


def _extract_metadata_csvs(
    zip_file: ZipFile,
    members: list[ZipInfo],
    *,
    metadata_dir: Path,
    source_id: str,
) -> list[Path]:
    output_paths: list[Path] = []

    for member in members:
        name = Path(member.filename).name
        lower_name = name.lower()

        if not lower_name.endswith(".csv") or not lower_name.startswith("metadata_"):
            continue

        output_name = _metadata_output_name(name, source_id=source_id)
        output_paths.append(
            extract_zip_member(zip_file, member, metadata_dir / output_name)
        )

    return output_paths


def _metadata_output_name(name: str, *, source_id: str) -> str:
    lower_name = name.lower()

    if lower_name.startswith("metadata_country_"):
        return f"{source_id}_country_metadata.csv"

    if lower_name.startswith("metadata_indicator_"):
        return f"{source_id}_indicator_metadata.csv"

    return f"{source_id}_{name}"


def _validate_indicator_code(
    path: Path, indicator_code: str, *, source_id: str
) -> None:
    expected = indicator_code.strip()
    if not expected:
        return

    try:
        content = path.read_text(encoding="utf-8-sig", errors="replace")
    except OSError as exc:
        raise NonRetryableWorldBankAcquisitionError(
            f"failed to read normalized World Bank CSV for source '{source_id}'"
        ) from exc

    if expected not in content:
        raise NonRetryableWorldBankAcquisitionError(
            f"downloaded World Bank CSV for source '{source_id}' does not contain "
            f"expected indicator code {expected!r}"
        )


def _safe_relative_output_path(path: str | Path) -> Path:
    candidate = Path(path)

    if candidate.is_absolute():
        return Path(candidate.name)

    safe_parts = [part for part in candidate.parts if part not in {"", "."}]
    if not safe_parts or any(part == ".." for part in safe_parts):
        raise NonRetryableWorldBankAcquisitionError(
            f"unsafe source path cannot be used as World Bank snapshot output: {path}"
        )

    return Path(*safe_parts)


def _path_relative_to(path: Path, root: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return str(path)
