from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

import pandas as pd


class SourceAdapter(ABC):
    """Compatibility-first adapter base class for source-to-canonical transforms."""

    def __init__(self) -> None:
        self.current_asset: Any | None = None
        self.current_source_spec: Any | None = None

    def prepare(self, asset: Any, *, source_spec: Any | None = None) -> None:
        """Store the current asset/spec for adapters that use a stateful compat path."""
        self.current_asset = asset
        self.current_source_spec = source_spec

    @abstractmethod
    def to_standardized_dataframe(self) -> pd.DataFrame:
        """Transform source data into the project's standardized metric format."""
