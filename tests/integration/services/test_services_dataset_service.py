from __future__ import annotations

from pathlib import Path

from country_compare.data.access import save_metric_dataframe
from country_compare.data.examples import build_example_metric_dataframe
from country_compare.data.stores.parquet_store import ParquetMetricStore
from country_compare.services import AppContext, DatasetService


def test_dataset_service_returns_summary_for_valid_dataset(tmp_path: Path) -> None:
    store_path = tmp_path / "metrics.parquet"
    store = ParquetMetricStore(store_path)

    df = build_example_metric_dataframe()
    save_metric_dataframe(df, store=store)

    service = DatasetService(AppContext(store_backend="parquet", store_path=store_path))
    summary = service.get_dataset_summary()

    assert summary.exists is True
    assert summary.row_count == len(df)
    assert summary.country_count == df["country_code"].nunique()
    assert summary.metric_count == df["metric_id"].nunique()
    assert summary.year_min == int(df["year"].min())
    assert summary.year_max == int(df["year"].max())
    assert {item.name for item in summary.categories} == {
        "economy",
        "governance",
        "health",
    }


def test_dataset_service_handles_missing_dataset_gracefully(tmp_path: Path) -> None:
    store_path = tmp_path / "missing.parquet"
    service = DatasetService(AppContext(store_backend="parquet", store_path=store_path))

    summary = service.get_dataset_summary()

    assert summary.exists is False
    assert summary.error is not None
    assert summary.error.code == "resource_not_found"
