from country_compare.data.examples import build_example_metric_dataframe
from country_compare.data.stores.parquet_store import ParquetMetricStore
from country_compare.data.validation import validate_and_parse_dataframe


def main() -> None:
    df = build_example_metric_dataframe()

    validate_and_parse_dataframe(df)

    store = ParquetMetricStore("data/processed/metrics.parquet")
    store.write_metrics(df)

    loaded_df = store.read_metrics()
    dataset = validate_and_parse_dataframe(loaded_df)

    print(f"Loaded {len(dataset.records)} records.")
    print(loaded_df.head())


if __name__ == "__main__":
    main()
