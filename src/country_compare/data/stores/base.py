from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Sequence

import pandas as pd


class MetricStore(ABC):
    """
    Backend-agnostic storage contract for canonical metric datasets.
    """

    @abstractmethod
    def write(self, data: pd.DataFrame) -> None:
        """Validate and persist the canonical metric dataset."""

    @abstractmethod
    def read(self, *, columns: Sequence[str] | None = None) -> pd.DataFrame:
        """Load and validate the canonical metric dataset."""

    def write_metrics(self, df: pd.DataFrame) -> None:
        # backward-compatible alias
        self.write(df)

    def read_metrics(self) -> pd.DataFrame:
        # backward-compatible alias
        return self.read()

    def exists(self) -> bool:
        raise NotImplementedError

    def delete(self) -> None:
        raise NotImplementedError
