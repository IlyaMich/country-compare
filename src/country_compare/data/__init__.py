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
from country_compare.data.models import MetricDataset, MetricMetadata, MetricRecord

__all__ = [
    "ALL_COLUMNS",
    "OPTIONAL_COLUMNS",
    "PRIMARY_KEY_COLUMNS",
    "REQUIRED_COLUMNS",
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
