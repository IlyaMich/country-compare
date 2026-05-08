from country_compare.data.access import (
    load_metric_dataframe,
    save_metric_dataframe,
)
from country_compare.data.examples import build_example_metric_dataframe
from country_compare.data.stores.parquet_store import ParquetMetricStore

store = ParquetMetricStore("data/processed/metrics.parquet")

df = build_example_metric_dataframe()
save_metric_dataframe(df, store=store)  # Validate -> persist

loaded = load_metric_dataframe(store=store)  # Load -> validate -> return
print(loaded.head())
