from __future__ import annotations

from abc import ABC, abstractmethod

import pandas as pd

from country_compare.prediction.errors import PredictionErrorCode, PredictionException
from country_compare.prediction.models import (
    ForecastContext,
    ForecastOptions,
    ForecastPoint,
    ForecasterInfo,
    RawForecastResult,
)

YEAR_COLUMN = "year"
VALUE_COLUMN = "value"


class BaseForecaster(ABC):
    method_id: str
    display_name: str
    description: str | None = None

    def info(self, metadata: dict | None = None) -> ForecasterInfo:
        return ForecasterInfo(
            method_id=self.method_id,
            display_name=self.display_name,
            description=self.description,
            metadata=metadata or {},
        )

    @abstractmethod
    def supports(
        self,
        series: pd.DataFrame,
        *,
        context: ForecastContext,
        options: ForecastOptions,
    ) -> tuple[bool, list[str]]:
        """Return whether this forecaster can forecast the prepared series."""

    @abstractmethod
    def forecast(
        self,
        series: pd.DataFrame,
        future_years: list[int],
        *,
        context: ForecastContext,
        options: ForecastOptions,
    ) -> RawForecastResult:
        """Return raw forecast points. Output shaping is handled separately."""

    def _require_supported(
        self,
        series: pd.DataFrame,
        *,
        context: ForecastContext,
        options: ForecastOptions,
    ) -> None:
        ok, reasons = self.supports(series, context=context, options=options)
        if ok:
            return
        raise PredictionException(
            PredictionErrorCode.INSUFFICIENT_HISTORY,
            "; ".join(reasons) or f"forecaster {self.method_id!r} does not support this series",
            country_code=context.country_code,
            metric_id=context.metric_id,
            details={"method": self.method_id, "reasons": reasons},
        )


class LastObservedForecaster(BaseForecaster):
    method_id = "last_observed"
    display_name = "Last observed value"
    description = "Repeats the most recent observed value for every forecast year."

    def supports(
        self,
        series: pd.DataFrame,
        *,
        context: ForecastContext,
        options: ForecastOptions,
    ) -> tuple[bool, list[str]]:
        if len(series.index) < 1:
            return False, ["last_observed requires at least one observation"]
        return True, []

    def forecast(
        self,
        series: pd.DataFrame,
        future_years: list[int],
        *,
        context: ForecastContext,
        options: ForecastOptions,
    ) -> RawForecastResult:
        self._require_supported(series, context=context, options=options)
        latest_value = float(pd.to_numeric(series[VALUE_COLUMN], errors="coerce").iloc[-1])
        points = [
            ForecastPoint(year=int(year), value=latest_value, horizon=index + 1)
            for index, year in enumerate(future_years)
        ]
        return RawForecastResult(
            method_id=self.method_id,
            points=points,
            forecaster_info=self.info(metadata={"latest_observed_value": latest_value}),
        )

class MovingAverageForecaster(BaseForecaster):
    method_id = "moving_average"
    display_name = "Moving average"
    description = "Repeats the mean of the most recent observations for every forecast year."
    default_window_size = 3
    minimum_observations = 2

    def supports(
        self,
        series: pd.DataFrame,
        *,
        context: ForecastContext,
        options: ForecastOptions,
    ) -> tuple[bool, list[str]]:
        values = pd.to_numeric(series[VALUE_COLUMN], errors="coerce").dropna()
        reasons: list[str] = []
        if len(series.index) < self.minimum_observations:
            reasons.append("moving_average requires at least two observations")
        if len(values.index) < len(series.index):
            reasons.append("moving_average requires numeric values for every observation")
        return len(reasons) == 0, reasons

    def forecast(
        self,
        series: pd.DataFrame,
        future_years: list[int],
        *,
        context: ForecastContext,
        options: ForecastOptions,
    ) -> RawForecastResult:
        self._require_supported(series, context=context, options=options)

        sorted_series = series.copy(deep=True)
        sorted_series[YEAR_COLUMN] = pd.to_numeric(sorted_series[YEAR_COLUMN], errors="coerce")
        sorted_series[VALUE_COLUMN] = pd.to_numeric(sorted_series[VALUE_COLUMN], errors="coerce")
        sorted_series = sorted_series.sort_values(by=YEAR_COLUMN, kind="mergesort")

        effective_window_size = min(self.default_window_size, len(sorted_series.index))
        window = sorted_series.tail(effective_window_size)
        moving_average_value = float(window[VALUE_COLUMN].mean())
        input_years_used = [int(year) for year in window[YEAR_COLUMN].tolist()]

        warnings: list[str] = []
        if effective_window_size < self.default_window_size:
            warnings.append(
                "moving_average used all available observations because fewer than "
                f"{self.default_window_size} observations were available"
            )

        points = [
            ForecastPoint(
                year=int(year),
                value=moving_average_value,
                horizon=index + 1,
            )
            for index, year in enumerate(future_years)
        ]
        metadata = {
            "window_size": self.default_window_size,
            "effective_window_size": effective_window_size,
            "input_years_used": input_years_used,
            "moving_average_value": moving_average_value,
        }
        return RawForecastResult(
            method_id=self.method_id,
            points=points,
            forecaster_info=self.info(metadata=metadata),
            diagnostics_metadata=metadata,
            warnings=warnings,
        )
    
class LinearTrendForecaster(BaseForecaster):
    method_id = "linear_trend"
    display_name = "Linear trend"
    description = "Fits a simple least-squares straight line to annual observations."

    def supports(
        self,
        series: pd.DataFrame,
        *,
        context: ForecastContext,
        options: ForecastOptions,
    ) -> tuple[bool, list[str]]:
        years = pd.to_numeric(series[YEAR_COLUMN], errors="coerce").dropna()
        values = pd.to_numeric(series[VALUE_COLUMN], errors="coerce").dropna()
        reasons: list[str] = []
        if len(series.index) < 3:
            reasons.append("linear_trend requires at least three observations")
        if years.nunique() < 3:
            reasons.append("linear_trend requires at least three distinct years")
        if len(values.index) < len(series.index):
            reasons.append("linear_trend requires numeric values for every observation")
        return len(reasons) == 0, reasons

    def forecast(
        self,
        series: pd.DataFrame,
        future_years: list[int],
        *,
        context: ForecastContext,
        options: ForecastOptions,
    ) -> RawForecastResult:
        self._require_supported(series, context=context, options=options)

        x = pd.to_numeric(series[YEAR_COLUMN], errors="coerce").astype("float64")
        y = pd.to_numeric(series[VALUE_COLUMN], errors="coerce").astype("float64")
        x_mean = float(x.mean())
        y_mean = float(y.mean())
        denominator = float(((x - x_mean) ** 2).sum())
        if denominator == 0.0:
            raise PredictionException(
                PredictionErrorCode.UNSUPPORTED_SERIES_SHAPE,
                "linear_trend cannot be fit because all observations have the same year",
                country_code=context.country_code,
                metric_id=context.metric_id,
            )

        slope = float(((x - x_mean) * (y - y_mean)).sum() / denominator)
        intercept = float(y_mean - slope * x_mean)
        points = [
            ForecastPoint(
                year=int(year),
                value=float(intercept + slope * float(year)),
                horizon=index + 1,
            )
            for index, year in enumerate(future_years)
        ]
        return RawForecastResult(
            method_id=self.method_id,
            points=points,
            forecaster_info=self.info(metadata={"slope": slope, "intercept": intercept}),
            diagnostics_metadata={"slope": slope, "intercept": intercept},
        )
