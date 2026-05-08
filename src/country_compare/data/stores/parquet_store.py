from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

import pandas as pd

from country_compare.data.stores.base import MetricStore
from country_compare.data.validation import (
    ValidationSettings,
    prepare_dataframe_for_read,
    prepare_dataframe_for_storage,
)


class ParquetMetricStore(MetricStore):
    """
    Parquet-backed implementation of the metric store interface.
    """

    def __init__(
        self,
        path: str | Path,
        *,
        validation_settings: ValidationSettings | None = None,
    ) -> None:
        self.path = Path(path)
        self.validation_settings = validation_settings or ValidationSettings()

    def write(self, data: pd.DataFrame) -> None:
        prepared = prepare_dataframe_for_storage(
            data,
            settings=self.validation_settings,
        )
        self.path.parent.mkdir(parents=True, exist_ok=True)
        prepared.to_parquet(self.path, index=False)

    def read(self, *, columns: Sequence[str] | None = None) -> pd.DataFrame:
        if not self.path.exists():
            raise FileNotFoundError(f"Metric dataset not found: {self.path}")

        loaded = pd.read_parquet(
            self.path,
            columns=list(columns) if columns is not None else None,
        )
        return prepare_dataframe_for_read(
            loaded,
            settings=self.validation_settings,
        )

    def exists(self) -> bool:
        return self.path.exists()

    def delete(self) -> None:
        if self.path.exists():
            self.path.unlink()
