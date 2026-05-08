from __future__ import annotations

import json
import os
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd

from country_compare.data.manifest import (
    DATASET_MANIFEST_FILENAME,
    build_manifest_from_dataframe_or_file,
    validate_manifest_against_dataset,
)
from country_compare.data.validation import prepare_dataframe_for_storage


@dataclass(frozen=True)
class OfflinePublishResult:
    """Result returned by the atomic offline dataset publish helper."""

    dataset_path: str
    manifest_path: str
    row_count: int
    sha256: str
    manifest: dict[str, Any]


def atomic_publish_metric_dataframe(
    dataframe: pd.DataFrame,
    *,
    dataset_path: str | Path,
    manifest_path: str | Path | None = None,
    dataset_version: str | None = None,
    source_manifest: str | None = None,
    pipeline_version: str | None = None,
    notes: str | None = None,
) -> OfflinePublishResult:
    """Atomically publish a validated offline metric dataset and manifest.

    This helper is intentionally not connected to the API. It writes a temporary
    parquet file and temporary manifest in the destination directory, validates
    both, then uses ``os.replace`` to move each artifact into its final name.
    """

    final_dataset_path = Path(dataset_path)
    final_manifest_path = (
        Path(manifest_path)
        if manifest_path is not None
        else final_dataset_path.with_name(DATASET_MANIFEST_FILENAME)
    )
    final_dataset_path.parent.mkdir(parents=True, exist_ok=True)
    final_manifest_path.parent.mkdir(parents=True, exist_ok=True)

    token = uuid.uuid4().hex
    temp_dataset_path = final_dataset_path.with_name(
        f".{final_dataset_path.name}.{token}.tmp.parquet"
    )
    temp_manifest_path = final_manifest_path.with_name(
        f".{final_manifest_path.name}.{token}.tmp"
    )

    try:
        prepared = prepare_dataframe_for_storage(dataframe)
        prepared.to_parquet(temp_dataset_path, index=False)

        manifest = build_manifest_from_dataframe_or_file(
            dataframe=prepared,
            dataset_path=temp_dataset_path,
            dataset_file=final_dataset_path.name,
            dataset_version=dataset_version,
            source_manifest=source_manifest,
            pipeline_version=pipeline_version,
            notes=notes,
        )
        temp_manifest_path.write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

        validation = validate_manifest_against_dataset(
            manifest_path=temp_manifest_path,
            dataset_path=temp_dataset_path,
            dataframe=prepared,
            expected_dataset_file=final_dataset_path.name,
        )
        if not validation.valid:
            messages = "; ".join(validation.messages) or "manifest validation failed"
            raise ValueError(messages)

        os.replace(temp_dataset_path, final_dataset_path)
        os.replace(temp_manifest_path, final_manifest_path)

        return OfflinePublishResult(
            dataset_path=str(final_dataset_path),
            manifest_path=str(final_manifest_path),
            row_count=int(manifest["row_count"]),
            sha256=str(manifest["sha256"]),
            manifest=manifest,
        )
    finally:
        for path in (temp_dataset_path, temp_manifest_path):
            try:
                if path.exists():
                    path.unlink()
            except OSError:
                pass
