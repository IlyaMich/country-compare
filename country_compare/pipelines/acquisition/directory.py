from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from pathlib import Path

from country_compare.pipelines.acquisition.base import RawAcquirer
from country_compare.pipelines.errors import SourceNotFoundError, UnsupportedFormatError
from country_compare.pipelines.models import AcquiredAsset, SourceSpec

_SUPPORTED_SUFFIXES: dict[str, str] = {
    ".csv": "csv",
    ".parquet": "parquet",
    ".pq": "parquet",
    ".xlsx": "excel",
    ".xls": "excel",
}


class DirectoryRawAcquirer(RawAcquirer):
    def acquire(
        self,
        source_spec: SourceSpec,
        *,
        raw_root: Path | None = None,
    ) -> list[AcquiredAsset]:
        root = Path(raw_root) if raw_root is not None else None
        paths = self._resolve_paths(source_spec, raw_root=root)
        if not paths:
            raise SourceNotFoundError(
                f"no files matched source '{source_spec.source_id}'"
            )

        assets: list[AcquiredAsset] = []
        for path in paths:
            file_format = self._detect_file_format(path, format_hint=source_spec.format_hint)
            stat = path.stat()
            assets.append(
                AcquiredAsset(
                    source_id=source_spec.source_id,
                    adapter_id=source_spec.adapter_id,
                    local_path=path,
                    file_format=file_format,
                    file_size=int(stat.st_size),
                    checksum=self._sha256(path),
                    modified_at=datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc),
                    metadata={
                        "source_path": str(path),
                    },
                )
            )
        return assets

    def _resolve_paths(self, source_spec: SourceSpec, *, raw_root: Path | None) -> list[Path]:
        if source_spec.path is not None:
            path = Path(source_spec.path)
            resolved = path if path.is_absolute() else (raw_root / path if raw_root is not None else path)
            if not resolved.exists():
                raise SourceNotFoundError(f"source path does not exist: {resolved}")
            if not resolved.is_file():
                raise SourceNotFoundError(f"source path is not a file: {resolved}")
            return [resolved.resolve()]

        assert source_spec.glob is not None
        search_root = raw_root if raw_root is not None else Path.cwd()
        matches = sorted(path.resolve() for path in search_root.glob(source_spec.glob) if path.is_file())
        if not matches:
            raise SourceNotFoundError(
                f"source glob matched no files: root={search_root} pattern={source_spec.glob}"
            )
        return matches

    def _detect_file_format(self, path: Path, *, format_hint: str | None = None) -> str:
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
