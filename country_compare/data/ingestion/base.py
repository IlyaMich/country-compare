from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

import pandas as pd


class SourceAdapter(ABC):
    def __init__(self) -> None:
        self.current_asset: Any | None = None
        self.current_source_spec: Any | None = None

    def prepare(self, asset: Any, *, source_spec: Any | None = None) -> None:
        self.current_asset = asset
        self.current_source_spec = source_spec

    def adapt(self, asset: Any, *, source_spec: Any | None = None) -> pd.DataFrame:
        self.prepare(asset, source_spec=source_spec)
        return self.to_standardized_dataframe()

    @abstractmethod
    def to_standardized_dataframe(self) -> pd.DataFrame:
        raise NotImplementedError
