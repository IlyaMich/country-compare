from __future__ import annotations

from collections.abc import Callable
from typing import Any

from country_compare.data.stores.base import MetricStore
from country_compare.data.stores.parquet_store import ParquetMetricStore
from country_compare.paths import PROCESSED_DATA_DIR

StoreFactory = Callable[..., MetricStore]


def _default_parquet_factory(**kwargs: Any) -> MetricStore:
    path = kwargs.pop("path", PROCESSED_DATA_DIR / "metrics.parquet")
    return ParquetMetricStore(path=path, **kwargs)


_STORE_FACTORIES: dict[str, StoreFactory] = {
    "parquet": _default_parquet_factory,
}


def register_metric_store(
    backend: str,
    factory: StoreFactory,
    *,
    overwrite: bool = False,
) -> None:
    normalized = backend.strip().lower()
    if not normalized:
        raise ValueError("backend name must not be empty")

    if normalized in _STORE_FACTORIES and not overwrite:
        raise ValueError(
            f"store backend '{normalized}' is already registered; "
            "pass overwrite=True to replace it"
        )

    _STORE_FACTORIES[normalized] = factory


def create_metric_store(
    backend: str = "parquet",
    **kwargs: Any,
) -> MetricStore:
    normalized = backend.strip().lower()
    if normalized not in _STORE_FACTORIES:
        available = ", ".join(sorted(_STORE_FACTORIES))
        raise ValueError(
            f"unknown metric store backend '{backend}'. Available backends: {available}"
        )
    return _STORE_FACTORIES[normalized](**kwargs)


def get_default_metric_store(**kwargs: Any) -> MetricStore:
    return create_metric_store("parquet", **kwargs)


def list_registered_backends() -> tuple[str, ...]:
    return tuple(sorted(_STORE_FACTORIES))
