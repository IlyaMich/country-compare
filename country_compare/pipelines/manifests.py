from __future__ import annotations

from collections.abc import Mapping
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, cast

import yaml

from country_compare.pipelines.models import ProcessingRequest, SourceSpec


@dataclass(slots=True)
class SourceManifest:
    sources: list[SourceSpec]
    raw_root: Path | None = None
    name: str | None = None
    defaults: dict[str, Any] = field(default_factory=dict)
    processing: dict[str, Any] = field(default_factory=dict)
    tags: tuple[str, ...] = ()
    labels: dict[str, str] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.raw_root is not None:
            self.raw_root = Path(self.raw_root)
        self.defaults = dict(self.defaults or {})
        self.processing = dict(self.processing or {})
        self.tags = tuple(
            str(value).strip() for value in (self.tags or ()) if str(value).strip()
        )
        self.labels = {
            str(key).strip(): str(value).strip()
            for key, value in (self.labels or {}).items()
            if str(key).strip()
        }
        self.metadata = dict(self.metadata or {})
        self.sources = _apply_manifest_defaults_to_sources(
            self.sources,
            defaults=self.defaults,
            tags=self.tags,
            labels=self.labels,
        )


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    merged = dict(base)
    for key, value in override.items():
        if isinstance(merged.get(key), dict) and isinstance(value, dict):
            merged[key] = _deep_merge(dict(merged[key]), value)
        elif key == "tags":
            seen: set[str] = set()
            values = []
            for item in [*(merged.get("tags", ()) or ()), *(value or ())]:
                text = str(item).strip()
                if not text or text in seen:
                    continue
                values.append(text)
                seen.add(text)
            merged[key] = tuple(values)
        else:
            merged[key] = value
    return merged


def _source_spec_payload(source: SourceSpec | Mapping[str, Any]) -> dict[str, Any]:
    if isinstance(source, SourceSpec):
        return asdict(source)
    return dict(source)


def _source_defaults_with_manifest_metadata(
    defaults: dict[str, Any] | None,
    *,
    tags: tuple[str, ...] = (),
    labels: dict[str, str] | None = None,
) -> dict[str, Any]:
    source_defaults = dict(defaults or {})
    if tags:
        source_defaults = _deep_merge(source_defaults, {"tags": tuple(tags)})
    if labels:
        source_defaults = _deep_merge(source_defaults, {"labels": dict(labels)})
    return source_defaults


def _apply_manifest_defaults_to_sources(
    sources: list[SourceSpec] | list[Mapping[str, Any]],
    *,
    defaults: dict[str, Any] | None,
    tags: tuple[str, ...] = (),
    labels: dict[str, str] | None = None,
) -> list[SourceSpec]:
    source_defaults = _source_defaults_with_manifest_metadata(
        defaults,
        tags=tags,
        labels=labels,
    )
    return [
        build_source_spec(_source_spec_payload(source), defaults=source_defaults)
        for source in sources
    ]


def build_source_spec(
    source_data: dict[str, Any], *, defaults: dict[str, Any] | None = None
) -> SourceSpec:
    return SourceSpec(**_deep_merge(dict(defaults or {}), dict(source_data)))


def build_source_specs(
    sources: list[dict[str, Any]], *, defaults: dict[str, Any] | None = None
) -> list[SourceSpec]:
    return [build_source_spec(source, defaults=defaults) for source in sources]


def load_source_manifest(path: str | Path) -> SourceManifest:
    manifest_path = Path(path)
    raw = yaml.safe_load(manifest_path.read_text(encoding="utf-8")) or {}
    if isinstance(raw, list):
        raw = {"sources": raw}
    if not isinstance(raw, dict):
        raise ValueError("source manifest must be a mapping or list")
    sources_raw = raw.get("sources") or []
    if not isinstance(sources_raw, list):
        raise ValueError("source manifest field 'sources' must be a list")
    source_payloads: list[dict[str, Any]] = []
    for source in sources_raw:
        if not isinstance(source, Mapping):
            raise ValueError("each source manifest item must be a mapping")
        source_payloads.append(dict(cast(Mapping[str, Any], source)))

    return SourceManifest(
        name=raw.get("name"),
        raw_root=raw.get("raw_root"),
        defaults=dict(raw.get("defaults") or {}),
        processing=dict(raw.get("processing") or {}),
        tags=tuple(raw.get("tags") or ()),
        labels=dict(raw.get("labels") or {}),
        metadata=dict(raw.get("metadata") or {}),
        sources=cast(list[SourceSpec], source_payloads),
    )


def manifest_to_processing_request(
    manifest: SourceManifest, **overrides: Any
) -> ProcessingRequest:
    payload = dict(manifest.processing)
    if manifest.raw_root is not None and "raw_root" not in payload:
        payload["raw_root"] = manifest.raw_root
    payload["sources"] = list(manifest.sources)
    payload.update(overrides)
    return ProcessingRequest(**payload)
