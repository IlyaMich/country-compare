from __future__ import annotations

from country_compare.data.ingestion.adapters.passthrough import (
    CANONICAL_TABULAR_PASSTHROUGH_ADAPTER_ID,
    CanonicalTabularPassthroughAdapter,
)
from country_compare.data.ingestion.adapters.wide_year_metric_csv import (
    WIDE_YEAR_METRIC_CSV_ADAPTER_ID,
    WideYearMetricCsvAdapter,
)

__all__ = [
    "CANONICAL_TABULAR_PASSTHROUGH_ADAPTER_ID",
    "CanonicalTabularPassthroughAdapter",
    "WIDE_YEAR_METRIC_CSV_ADAPTER_ID",
    "WideYearMetricCsvAdapter",
]
