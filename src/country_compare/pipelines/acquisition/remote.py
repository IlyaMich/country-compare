from __future__ import annotations

import hashlib
import shutil
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Final
from urllib.parse import unquote, urlparse
from urllib.request import Request, url2pathname, urlopen

from country_compare.pipelines.acquisition.base import RawAcquirer
from country_compare.pipelines.acquisition.directory import DirectoryRawAcquirer
from country_compare.pipelines.errors import (
    SourceNotFoundError,
    SourcePullError,
    UnsupportedFormatError,
)
from country_compare.pipelines.models import AcquiredAsset, SourceSpec

_SUPPORTED_SUFFIXES: Final[dict[str, str]] = {
    ".csv": "csv",
    ".parquet": "parquet",
    ".pq": "parquet",
    ".xlsx": "excel",
    ".xls": "excel",
}


class RemoteRawAcquirer(RawAcquirer):
    """Materialize a remote asset into a local file and return a standard AcquiredAsset."""

    def acquire(
        self,
        source_spec: SourceSpec,
        *,
        raw_root: Path | None = None,
    ) -> list[AcquiredAsset]:
        remote_url = (source_spec.remote_url or "").strip()
        if not remote_url:
            raise SourcePullError(
                f"source '{source_spec.source_id}' does not define remote_url"
            )

        destination_dir = self._resolve_destination_dir(source_spec, raw_root=raw_root)
        destination_dir.mkdir(parents=True, exist_ok=True)
        destination_path = destination_dir / self._resolve_filename(source_spec)

        self._materialize_remote_file(remote_url, destination_path)
        file_format = self._detect_file_format(
            destination_path, format_hint=source_spec.format_hint
        )
        stat = destination_path.stat()
        return [
            AcquiredAsset(
                source_id=source_spec.source_id,
                adapter_id=source_spec.adapter_id,
                local_path=destination_path.resolve(),
                file_format=file_format,
                file_size=int(stat.st_size),
                checksum=self._sha256(destination_path),
                modified_at=datetime.fromtimestamp(stat.st_mtime, tz=UTC),
                metadata={
                    "source_path": str(destination_path.resolve()),
                    "remote_url": remote_url,
                    "acquisition_mode": "remote_pull",
                },
            )
        ]

    @staticmethod
    def _resolve_destination_dir(
        source_spec: SourceSpec, *, raw_root: Path | None
    ) -> Path:
        if raw_root is not None:
            return Path(raw_root) / ".acquired" / source_spec.source_id
        return (
            Path(tempfile.gettempdir())
            / "country_compare"
            / "acquired"
            / source_spec.source_id
        )

    @staticmethod
    def _resolve_filename(source_spec: SourceSpec) -> str:
        if source_spec.download_filename:
            return source_spec.download_filename

        parsed = urlparse(source_spec.remote_url or "")
        candidate = Path(unquote(parsed.path)).name.strip()
        if candidate:
            return candidate

        suffix = {
            "csv": ".csv",
            "parquet": ".parquet",
            "excel": ".xlsx",
        }.get((source_spec.format_hint or "").strip().lower(), ".bin")
        return f"{source_spec.source_id}{suffix}"

    def _materialize_remote_file(self, remote_url: str, destination_path: Path) -> None:
        parsed = urlparse(remote_url)
        scheme = parsed.scheme.lower()

        if scheme == "file":
            url_path = unquote(parsed.path)

            # Preserve UNC hosts if present, but ignore localhost.
            if parsed.netloc and parsed.netloc.lower() != "localhost":
                url_path = f"//{parsed.netloc}{url_path}"

            source_path = Path(url2pathname(url_path))

            if not source_path.exists() or not source_path.is_file():
                raise SourceNotFoundError(
                    f"remote file URL does not exist: {remote_url}"
                )

            shutil.copyfile(source_path, destination_path)
            return

        if scheme not in {"http", "https"}:
            raise SourcePullError(
                f"unsupported remote_url scheme '{parsed.scheme}' for source pull: {remote_url}"
            )

        request = Request(
            remote_url, headers={"User-Agent": "country-compare/processing-pipeline"}
        )
        try:
            with (
                urlopen(request, timeout=30) as response,
                destination_path.open("wb") as handle,
            ):
                shutil.copyfileobj(response, handle)
        except Exception as exc:
            raise SourcePullError(
                f"failed to download remote source: {remote_url}"
            ) from exc

    @staticmethod
    def _detect_file_format(path: Path, *, format_hint: str | None = None) -> str:
        if format_hint:
            normalized = str(format_hint).strip().lower()
            if normalized in {"csv", "parquet", "excel"}:
                return normalized
        try:
            return _SUPPORTED_SUFFIXES[path.suffix.lower()]
        except KeyError as exc:
            raise UnsupportedFormatError(
                f"unsupported file format for path '{path}': suffix='{path.suffix}'"
            ) from exc

    @staticmethod
    def _sha256(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()


class CompositeRawAcquirer(RawAcquirer):
    """Default acquirer that supports both local directory inputs and remote pulls."""

    def __init__(
        self,
        *,
        directory_acquirer: RawAcquirer | None = None,
        remote_acquirer: RawAcquirer | None = None,
    ) -> None:
        self.directory_acquirer = directory_acquirer or DirectoryRawAcquirer()
        self.remote_acquirer = remote_acquirer or RemoteRawAcquirer()

    def acquire(
        self,
        source_spec: SourceSpec,
        *,
        raw_root: Path | None = None,
    ) -> list[AcquiredAsset]:
        if source_spec.path is not None or source_spec.glob is not None:
            return self.directory_acquirer.acquire(source_spec, raw_root=raw_root)
        if source_spec.remote_url is not None:
            return self.remote_acquirer.acquire(source_spec, raw_root=raw_root)
        raise SourceNotFoundError(
            f"source '{source_spec.source_id}' did not provide path, glob, or remote_url"
        )
