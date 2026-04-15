from __future__ import annotations

from abc import ABC, abstractmethod

import pandas as pd


class MetricStore(ABC):
    """
    Abstract storage interface for canonical metric data.

    All application code should interact with this abstraction rather than
    touching the backend format directly.
    """

    @abstractmethod
    def write_metrics(self, df: pd.DataFrame) -> None:
        raise NotImplementedError

    @abstractmethod
    def read_metrics(self) -> pd.DataFrame:
        raise NotImplementedError

    def exists(self) -> bool:
        raise NotImplementedError
