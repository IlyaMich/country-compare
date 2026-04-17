from __future__ import annotations

import pandas as pd
import pytest

from country_compare.data.access import (
    delete_metric_dataset,
    load_metric_dataframe,
    load_metric_dataset,
    metric_dataset_exists,
    save_metric_dataframe,
    save_metric_dataset,
)
from country_compare.data.examples import build_example_metric_dataframe, build_example_metric_dataset
from country_compare.data.stores.parquet_store import ParquetMetricStore
from country_compare.data.stores.registry import (
    create_metric_store,
    list_registered_backends,
    register_metric_store,
)


def test_parquet_store_read_write_roundtrip(tmp_path) -> None:
    df = build_example_metric_dataframe()
    store = ParquetMetricStore(tmp_path / "metrics.parquet")

    store.write(df)
    loaded = store.read()

    pd.testing.assert_frame_equal(loaded.reset_index(drop=True), df.reset_index(drop=True), check_dtype=False)


def test_parquet_store_validates_before_write(tmp_path) -> None:
    df = build_example_metric_dataframe().copy()
    df.loc[0, "country_code"] = "Israel"
    store = ParquetMetricStore(tmp_path / "metrics.parquet")

    with pytest.raises(ValueError, match="country_code must be 3 uppercase letters"):
        store.write(df)


def test_parquet_store_validates_after_read(tmp_path) -> None:
    df = build_example_metric_dataframe().copy()
    path = tmp_path / "metrics.parquet"
    df.to_parquet(path, index=False)

    raw = pd.read_parquet(path)
    raw.loc[0, "year"] = 1800
    raw.to_parquet(path, index=False)

    store = ParquetMetricStore(path)

    with pytest.raises(ValueError, match="year must be between 1900 and 2100"):
        store.read()


def test_access_helpers_use_store_boundary(tmp_path) -> None:
    df = build_example_metric_dataframe()
    dataset = build_example_metric_dataset()
    store = ParquetMetricStore(tmp_path / "metrics.parquet")

    save_metric_dataframe(df, store=store)
    assert metric_dataset_exists(store=store)

    loaded_df = load_metric_dataframe(store=store)
    loaded_dataset = load_metric_dataset(store=store)

    assert len(loaded_df) == len(df)
    assert len(loaded_dataset.records) == len(dataset.records)

    delete_metric_dataset(store=store)
    assert not metric_dataset_exists(store=store)

    save_metric_dataset(dataset, store=store)
    assert metric_dataset_exists(store=store)


def test_registry_supports_future_backends() -> None:
    class DummyStore:
        def write(self, data):
            self.data = data

        def read(self, *, columns=None):
            return getattr(self, "data", pd.DataFrame())

        def exists(self):
            return hasattr(self, "data")

        def delete(self):
            self.data = pd.DataFrame()

    register_metric_store("dummy", lambda **kwargs: DummyStore(), overwrite=True)

    store = create_metric_store("dummy")
    assert "dummy" in list_registered_backends()
    assert store.exists() is False
