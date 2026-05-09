from __future__ import annotations

import argparse
from pathlib import Path

from country_compare.data.access import load_metric_dataframe
from country_compare.data.catalog import (
    build_metadata_catalog,
    catalog_path_for_dataset,
    write_metadata_catalog,
)
from country_compare.data.manifest import (
    default_manifest_path_for_dataset,
    read_manifest,
)
from country_compare.data.stores.parquet_store import ParquetMetricStore


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Generate data/processed/catalog.json for the processed metric dataset."
    )
    parser.add_argument(
        "--dataset-path",
        default="data/processed/metrics.parquet",
        help="Path to the canonical processed metric parquet file.",
    )
    parser.add_argument(
        "--catalog-path",
        default=None,
        help="Optional output path. Defaults to catalog.json beside the dataset.",
    )
    args = parser.parse_args()

    dataset_path = Path(args.dataset_path)
    output_path = (
        Path(args.catalog_path)
        if args.catalog_path
        else catalog_path_for_dataset(dataset_path)
    )
    dataframe = load_metric_dataframe(store=ParquetMetricStore(dataset_path))
    identity = _read_identity(dataset_path)
    catalog = build_metadata_catalog(dataframe, identity=identity)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    write_metadata_catalog(catalog, output_path)
    print(output_path)
    return 0


def _read_identity(dataset_path: Path) -> dict[str, str]:
    manifest_path = default_manifest_path_for_dataset(dataset_path)
    if not manifest_path.exists():
        return {}
    try:
        manifest = read_manifest(manifest_path)
    except Exception:
        return {}
    mapping = {
        "dataset_version": "dataset_version",
        "dataset_sha256": "sha256",
        "dataset_file": "dataset_file",
        "dataset_created_at": "created_at",
        "schema_version": "schema_version",
    }
    return {
        output_key: str(manifest[manifest_key])
        for output_key, manifest_key in mapping.items()
        if manifest.get(manifest_key) is not None
    }


if __name__ == "__main__":
    raise SystemExit(main())
