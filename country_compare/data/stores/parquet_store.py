from __future__ import annotations

from pathlib import Path

import pandas as pd

from country_compare.data.stores.base import MetricStore


class ParquetMetricStore(MetricStore):
    """
    Parquet-backed implementation of the metric store interface.
    """

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    def write_metrics(self, df: pd.DataFrame) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        df.to_parquet(self.path, index=False)

    def read_metrics(self) -> pd.DataFrame:
        if not self.path.exists():
            raise FileNotFoundError(f"Metric dataset not found: {self.path}")
        return pd.read_parquet(self.path)

    def exists(self) -> bool:
        return self.path.exists()
