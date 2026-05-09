from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from country_compare.data.manifest import (
    DATASET_MANIFEST_FILENAME,
    build_manifest_from_dataframe_or_file,
    validate_manifest_against_dataset,
)

dataset_path = Path("data/processed/metrics.parquet")
manifest_path = dataset_path.with_name(DATASET_MANIFEST_FILENAME)

if not dataset_path.exists():
    raise SystemExit(f"Dataset not found: {dataset_path}")

dataframe = pd.read_parquet(dataset_path)

manifest = build_manifest_from_dataframe_or_file(
    dataframe=dataframe,
    dataset_path=dataset_path,
    dataset_file=dataset_path.name,
    pipeline_version="manual-existing-dataset-manifest",
    notes="Generated from existing processed dataset for API readiness.",
)

manifest_path.write_text(
    json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
    encoding="utf-8",
)

validation = validate_manifest_against_dataset(
    manifest_path=manifest_path,
    dataset_path=dataset_path,
    dataframe=dataframe,
)

if not validation.valid:
    raise SystemExit("Manifest validation failed: " + "; ".join(validation.messages))

print(f"Wrote and validated {manifest_path}")
