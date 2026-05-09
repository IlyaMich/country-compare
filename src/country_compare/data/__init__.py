"""Data layer: contract, validation, typed models, stores, and ingestion abstractions."""

from country_compare.data.access import (
    delete_metric_dataset,
    load_metric_dataframe,
    load_metric_dataset,
    metric_dataset_exists,
    save_metric_dataframe,
    save_metric_dataset,
)
from country_compare.data.contract import (
    ALL_COLUMNS,
    OPTIONAL_COLUMNS,
    PRIMARY_KEY_COLUMNS,
    REQUIRED_COLUMNS,
)
from country_compare.data.manifest import (
    DATASET_MANIFEST_FILENAME,
    DATASET_SCHEMA_VERSION,
    ManifestValidationIssue,
    ManifestValidationResult,
    build_manifest_from_dataframe_or_file,
    compute_file_sha256,
    default_manifest_path_for_dataset,
    read_manifest,
    validate_manifest_against_dataset,
)
from country_compare.data.models import MetricDataset, MetricMetadata, MetricRecord
from country_compare.data.publish import (
    OfflinePublishResult,
    atomic_publish_metric_dataframe,
)

__all__ = [
    "ALL_COLUMNS",
    "OPTIONAL_COLUMNS",
    "PRIMARY_KEY_COLUMNS",
    "REQUIRED_COLUMNS",
    "DATASET_MANIFEST_FILENAME",
    "DATASET_SCHEMA_VERSION",
    "ManifestValidationIssue",
    "ManifestValidationResult",
    "build_manifest_from_dataframe_or_file",
    "compute_file_sha256",
    "default_manifest_path_for_dataset",
    "read_manifest",
    "validate_manifest_against_dataset",
    "OfflinePublishResult",
    "atomic_publish_metric_dataframe",
    "MetricRecord",
    "MetricDataset",
    "MetricMetadata",
    "load_metric_dataframe",
    "save_metric_dataframe",
    "load_metric_dataset",
    "save_metric_dataset",
    "metric_dataset_exists",
    "delete_metric_dataset",
]
