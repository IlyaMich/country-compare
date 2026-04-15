from __future__ import annotations

from abc import ABC, abstractmethod

import pandas as pd


class SourceAdapter(ABC):
    @abstractmethod
    def to_standardized_dataframe(self) -> pd.DataFrame:
        """Transform source data into the project's standardized metric format."""
