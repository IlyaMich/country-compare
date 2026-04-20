from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

import pandas as pd
from matplotlib.figure import Figure

MessageLevel = Literal["info", "success", "warning", "error"]


@dataclass(slots=True)
class AppMessage:
    level: MessageLevel
    text: str
    detail: str | None = None


@dataclass(slots=True)
class ComparisonResult:
    mode: str
    request: Any
    dataframe: pd.DataFrame | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    diagnostics: dict[str, Any] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    error: Any | None = None

    @property
    def ok(self) -> bool:
        return self.error is None and self.dataframe is not None


@dataclass(slots=True)
class PresentationResult:
    mode: str
    request: Any
    summary: dict[str, Any] = field(default_factory=dict)
    table: pd.DataFrame | None = None
    chart: Figure | None = None
    tables: dict[str, pd.DataFrame] = field(default_factory=dict)
    charts: dict[str, Figure] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)
    diagnostics: dict[str, Any] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    messages: list[AppMessage] = field(default_factory=list)
    error: Any | None = None

    @property
    def ok(self) -> bool:
        return self.error is None and (
            self.table is not None or bool(self.tables) or self.chart is not None or bool(self.charts)
        )