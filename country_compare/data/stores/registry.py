from country_compare.data.stores.parquet_store import ParquetMetricStore
from country_compare.paths import PROCESSED_DATA_DIR


def get_default_metric_store() -> ParquetMetricStore:
    return ParquetMetricStore(PROCESSED_DATA_DIR / "metrics.parquet")
