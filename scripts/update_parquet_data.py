from country_compare.data.examples import build_example_metric_dataframe
from country_compare.data.access import save_metric_dataframe
from country_compare.data.stores.registry import create_metric_store

df = build_example_metric_dataframe()

store = create_metric_store("parquet")  # or pass path=..
save_metric_dataframe(df, store=store)

print("rows:", len(df))
print("countries:", df["country_code"].nunique())
print("metrics:", df["metric_id"].nunique())
print("years:", sorted(df["year"].astype(int).unique().tolist()))