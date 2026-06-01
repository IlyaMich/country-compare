from __future__ import annotations

import pandas as pd
import pytest

from country_compare.data.access import (
    delete_metric_dataset,
    load_metric_dataframe,
    metric_dataset_exists,
    save_metric_dataframe,
)
from country_compare.data.contract import REQUIRED_COLUMNS
from country_compare.data.examples import build_example_metric_dataframe
from country_compare.data.stores.parquet_store import ParquetMetricStore

pytestmark = pytest.mark.integration


def test_parquet_metric_store_roundtrip_preserves_canonical_dataset(tmp_path) -> None:
    source_dataframe = build_example_metric_dataframe()
    store = ParquetMetricStore(tmp_path / "metrics.parquet")

    save_metric_dataframe(source_dataframe, store=store)

    assert metric_dataset_exists(store=store)

    loaded_dataframe = load_metric_dataframe(store=store)

    sort_columns = ["country_code", "metric_id", "year"]
    expected = source_dataframe.sort_values(sort_columns).reset_index(drop=True)
    actual = loaded_dataframe.sort_values(sort_columns).reset_index(drop=True)

    pd.testing.assert_frame_equal(actual, expected, check_dtype=False)


def test_parquet_metric_store_supports_canonical_column_projection(tmp_path) -> None:
    source_dataframe = build_example_metric_dataframe()
    store = ParquetMetricStore(tmp_path / "metrics.parquet")

    save_metric_dataframe(source_dataframe, store=store)

    projected = load_metric_dataframe(
        store=store,
        columns=list(REQUIRED_COLUMNS),
    )

    assert set(REQUIRED_COLUMNS).issubset(projected.columns)
    assert len(projected) == len(source_dataframe)


def test_parquet_metric_store_rejects_non_canonical_partial_projection(
    tmp_path,
) -> None:
    source_dataframe = build_example_metric_dataframe()
    store = ParquetMetricStore(tmp_path / "metrics.parquet")

    save_metric_dataframe(source_dataframe, store=store)

    with pytest.raises(ValueError, match="Missing required columns"):
        load_metric_dataframe(
            store=store,
            columns=["country_code", "metric_id", "year", "value"],
        )


def test_parquet_metric_store_delete_removes_dataset(tmp_path) -> None:
    source_dataframe = build_example_metric_dataframe()
    store = ParquetMetricStore(tmp_path / "metrics.parquet")

    save_metric_dataframe(source_dataframe, store=store)

    assert metric_dataset_exists(store=store)

    delete_metric_dataset(store=store)

    assert not metric_dataset_exists(store=store)
