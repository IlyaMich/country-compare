from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

import pandas as pd


@dataclass(slots=True)
class AdapterResult:
    dataframe: pd.DataFrame
    raw_row_count: int = 0
    issues: list[Any] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


class SourceAdapter(ABC):
    def __init__(self) -> None:
        self.current_asset: Any | None = None
        self.current_source_spec: Any | None = None

    def prepare(self, asset: Any, *, source_spec: Any | None = None) -> None:
        self.current_asset = asset
        self.current_source_spec = source_spec

    def process(self, assets: list[Any], *, source_spec: Any | None = None) -> pd.DataFrame | AdapterResult:
        if not assets:
            raise ValueError("adapter received no acquired assets")
        if len(assets) != 1:
            raise ValueError(
                f"{self.__class__.__name__} expects exactly one asset, received {len(assets)}"
            )
        self.prepare(assets[0], source_spec=source_spec)
        return self.to_standardized_dataframe()

    @abstractmethod
    def to_standardized_dataframe(self) -> pd.DataFrame | AdapterResult:
        """Transform source data into the project's standardized metric format."""
