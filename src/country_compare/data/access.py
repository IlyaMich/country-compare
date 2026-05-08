from __future__ import annotations

import pandas as pd

from country_compare.data.models import MetricDataset
from country_compare.data.stores.base import MetricStore
from country_compare.data.stores.registry import get_default_metric_store
from country_compare.data.validation import (
    dataframe_to_metric_dataset,
    metric_dataset_to_dataframe,
)


def _resolve_store(store: MetricStore | None = None) -> MetricStore:
    return store if store is not None else get_default_metric_store()


def load_metric_dataframe(
    store: MetricStore | None = None,
    *,
    columns: list[str] | None = None,
) -> pd.DataFrame:
    return _resolve_store(store).read(columns=columns)


def save_metric_dataframe(
    dataframe: pd.DataFrame,
    store: MetricStore | None = None,
) -> None:
    _resolve_store(store).write(dataframe)


def load_metric_dataset(store: MetricStore | None = None) -> MetricDataset:
    dataframe = load_metric_dataframe(store=store)
    return dataframe_to_metric_dataset(dataframe)


def save_metric_dataset(
    dataset: MetricDataset,
    store: MetricStore | None = None,
) -> None:
    dataframe = metric_dataset_to_dataframe(dataset)
    save_metric_dataframe(dataframe, store=store)


def metric_dataset_exists(store: MetricStore | None = None) -> bool:
    return _resolve_store(store).exists()


def delete_metric_dataset(store: MetricStore | None = None) -> None:
    _resolve_store(store).delete()
