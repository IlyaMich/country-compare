from __future__ import annotations

from pathlib import Path
from typing import Any

from country_compare.pipelines.engine import PipelineEngine
from country_compare.pipelines.manifests import (
    SourceManifest,
    load_source_manifest,
    manifest_to_processing_request,
)
from country_compare.pipelines.models import ProcessingRequest, ProcessingResult

ManifestInput = SourceManifest | str | Path


def _coerce_manifest(manifest: ManifestInput) -> SourceManifest:
    if isinstance(manifest, SourceManifest):
        return manifest
    return load_source_manifest(manifest)


def load_processing_request_from_manifest(
    manifest: ManifestInput,
    **overrides: Any,
) -> ProcessingRequest:
    resolved_manifest = _coerce_manifest(manifest)
    return manifest_to_processing_request(resolved_manifest, **overrides)


def run_processing_manifest(
    manifest: ManifestInput,
    *,
    engine: PipelineEngine | None = None,
    **overrides: Any,
) -> ProcessingResult:
    request = load_processing_request_from_manifest(manifest, **overrides)
    resolved_engine = engine or PipelineEngine()
    return resolved_engine.run(request)
