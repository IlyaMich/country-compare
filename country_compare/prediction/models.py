from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Literal

import pandas as pd

from country_compare.prediction.errors import PredictionErrorCode


class PredictionMethod(str, Enum):
    LAST_OBSERVED = "last_observed"
    LINEAR_TREND = "linear_trend"


class PredictionDiagnosticStatus(str, Enum):
    OK = "ok"
    WARNING = "warning"
    FAILED = "failed"


@dataclass(frozen=True, slots=True)
class PredictionError:
    code: PredictionErrorCode
    message: str
    severity: Literal["warning", "error"] = "error"
    country_code: str | None = None
    metric_id: str | None = None
    year: int | None = None
    details: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class SingleMetricPredictionRequest:
    """Request for forecasting one country/metric annual time series."""

    country_code: str
    metric_id: str
    horizon_years: int
    method: PredictionMethod | str | None = None
    include_actuals: bool = True
    history_start_year: int | None = None
    history_end_year: int | None = None
    fallback_method: PredictionMethod | str | None = PredictionMethod.LAST_OBSERVED
    fail_on_warning: bool = False
    scenario_id: str = "baseline"

    def __post_init__(self) -> None:
        country_code = str(self.country_code).strip().upper()
        metric_id = str(self.metric_id).strip()
        scenario_id = str(self.scenario_id).strip() or "baseline"

        if not country_code:
            raise ValueError("country_code must not be empty")
        if not metric_id:
            raise ValueError("metric_id must not be empty")
        if " " in metric_id:
            raise ValueError("metric_id must not contain spaces; use snake_case.")
        if (
            self.history_start_year is not None
            and self.history_end_year is not None
            and int(self.history_start_year) > int(self.history_end_year)
        ):
            raise ValueError("history_start_year must be <= history_end_year")

        object.__setattr__(self, "country_code", country_code)
        object.__setattr__(self, "metric_id", metric_id)
        object.__setattr__(self, "horizon_years", int(self.horizon_years))
        object.__setattr__(self, "scenario_id", scenario_id)
        if self.history_start_year is not None:
            object.__setattr__(self, "history_start_year", int(self.history_start_year))
        if self.history_end_year is not None:
            object.__setattr__(self, "history_end_year", int(self.history_end_year))


@dataclass(frozen=True, slots=True)
class ForecastOptions:
    max_horizon_years: int = 10
    scenario_id: str = "baseline"


@dataclass(frozen=True, slots=True)
class ForecastContext:
    country_code: str
    metric_id: str
    forecast_origin_year: int
    horizon_years: int
    history_observation_count: int
    country_name: str | None = None
    metric_name: str | None = None
    unit: str | None = None
    category: str | None = None
    higher_is_better: bool | None = None
    source_name: str | None = None
    source_url: str | None = None
    training_start_year: int | None = None
    training_end_year: int | None = None
    dataset_version: str | None = None
    region: str | None = None
    income_group: str | None = None
    notes: str | None = None
    missing_years: list[int] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class ForecasterInfo:
    method_id: str
    display_name: str
    description: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class PredictionDiagnostics:
    status: PredictionDiagnosticStatus
    country_code: str | None = None
    metric_id: str | None = None
    method_requested: str | None = None
    method_used: str | None = None
    fallback_used: bool = False
    history_observation_count: int = 0
    training_start_year: int | None = None
    training_end_year: int | None = None
    forecast_origin_year: int | None = None
    missing_years: list[int] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    errors: list[PredictionError] = field(default_factory=list)

    @property
    def messages(self) -> list[str]:
        return [*self.warnings, *[error.message for error in self.errors]]


@dataclass(frozen=True, slots=True)
class ForecastPoint:
    year: int
    value: float
    horizon: int


@dataclass(frozen=True, slots=True)
class RawForecastResult:
    method_id: str
    points: list[ForecastPoint]
    forecaster_info: ForecasterInfo
    diagnostics_metadata: dict[str, Any] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class PreparedTimeSeries:
    series_df: pd.DataFrame
    future_years: list[int]
    context: ForecastContext
    warnings: list[str] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class PredictionResult:
    request: SingleMetricPredictionRequest
    forecast_df: pd.DataFrame
    combined_df: pd.DataFrame
    comparison_ready_df: pd.DataFrame
    diagnostics: list[PredictionDiagnostics]
    forecaster_info: list[ForecasterInfo]
    metadata: dict[str, Any] = field(default_factory=dict)
