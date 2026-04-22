from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

import pandas as pd


class SourceAdapter(ABC):
    """
    Backward-compatible base class for source adapters.

    Existing implementations may continue to override
    ``to_standardized_dataframe()`` with no arguments.

    Newer pipeline-aware adapters can override ``adapt(...)`` or ``process(...)``
    and use the staged ``current_asset`` / ``current_source_spec`` properties.
    """

    def __init__(self) -> None:
        self._current_asset: Any | None = None
        self._current_source_spec: Any | None = None

    @property
    def current_asset(self) -> Any | None:
        return self._current_asset

    @property
    def current_source_spec(self) -> Any | None:
        return self._current_source_spec

    def prepare(self, asset: Any, *, source_spec: Any | None = None) -> None:
        self._current_asset = asset
        self._current_source_spec = source_spec

    def adapt(self, asset: Any, *, source_spec: Any | None = None) -> pd.DataFrame:
        self.prepare(asset, source_spec=source_spec)
        return self.to_standardized_dataframe()

    def process(self, assets: list[Any], *, source_spec: Any | None = None) -> pd.DataFrame:
        if not assets:
            raise ValueError("adapter received no acquired assets")
        if len(assets) != 1:
            raise ValueError(
                f"adapter expected exactly one acquired asset, received {len(assets)}"
            )
        return self.adapt(assets[0], source_spec=source_spec)

    @abstractmethod
    def to_standardized_dataframe(self) -> pd.DataFrame:
        """Transform source data into the project's standardized metric format."""
