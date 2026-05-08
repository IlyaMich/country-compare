from __future__ import annotations

from collections.abc import Callable
from threading import RLock
from typing import TypeAlias

import pandas as pd

from country_compare.data.access import load_metric_dataframe
from country_compare.data.stores.base import MetricStore

DatasetCacheKey: TypeAlias = tuple[str, str]

_CACHE_LOCK = RLock()
_METRIC_DATAFRAME_CACHE: dict[DatasetCacheKey, pd.DataFrame] = {}


def get_cached_metric_dataframe(
    key: DatasetCacheKey,
    *,
    store: MetricStore,
    loader: Callable[..., pd.DataFrame] = load_metric_dataframe,
) -> pd.DataFrame:
    """Load the canonical metric dataframe once per process and return copies.

    Deployed API datasets are immutable between process restarts. Caching avoids
    repeated parquet reads while defensive copies prevent request code from
    mutating the process-local canonical dataframe.
    """

    with _CACHE_LOCK:
        cached = _METRIC_DATAFRAME_CACHE.get(key)
        if cached is None:
            cached = loader(store=store).copy(deep=True)
            _METRIC_DATAFRAME_CACHE[key] = cached
        return cached.copy(deep=True)


def clear_metric_dataframe_cache() -> None:
    """Clear the process-local dataframe cache. Intended for tests/restarts."""

    with _CACHE_LOCK:
        _METRIC_DATAFRAME_CACHE.clear()
