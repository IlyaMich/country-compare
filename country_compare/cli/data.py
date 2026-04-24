from __future__ import annotations

from pathlib import Path

from country_compare.data.access import load_metric_dataframe
from country_compare.data.stores.registry import create_metric_store
from country_compare.data.validation import validate_dataframe


def validate_data(
    *, store_backend: str = "parquet", store_path: str | Path | None = None
) -> int:
    store_kwargs = {"path": Path(store_path)} if store_path is not None else {}
    store = create_metric_store(store_backend, **store_kwargs)
    dataframe = load_metric_dataframe(store=store)
    result = validate_dataframe(dataframe)
    result.raise_if_invalid()
    return len(dataframe.index)
