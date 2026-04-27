from __future__ import annotations

from typing import Self

from pydantic import Field, field_validator, model_validator

from country_compare.api.schemas.common import StrictBaseModel
from country_compare.prediction import PredictionMethod


class BasePredictionRequest(StrictBaseModel):
    country_codes: list[str] = Field(min_length=1)
    metric_id: str = Field(min_length=1)
    method: PredictionMethod | None = PredictionMethod.LINEAR_TREND
    fallback_method: PredictionMethod | None = PredictionMethod.LAST_OBSERVED
    history_start_year: int | None = None
    history_end_year: int | None = None
    scenario_id: str = Field(default="baseline", min_length=1)

    @field_validator("country_codes")
    @classmethod
    def normalize_country_codes(cls, values: list[str]) -> list[str]:
        normalized: list[str] = []
        seen: set[str] = set()
        for value in values:
            text = str(value).strip().upper()
            if not text or text in seen:
                continue
            normalized.append(text)
            seen.add(text)

        if not normalized:
            raise ValueError("country_codes must contain at least one country code")

        return normalized

    @field_validator("metric_id")
    @classmethod
    def normalize_metric_id(cls, value: str) -> str:
        metric_id = str(value).strip()
        if not metric_id:
            raise ValueError("metric_id must be provided")
        return metric_id

    @field_validator("scenario_id")
    @classmethod
    def normalize_scenario_id(cls, value: str) -> str:
        return str(value).strip() or "baseline"

    @model_validator(mode="after")
    def validate_history_window(self) -> Self:
        if (
            self.history_start_year is not None
            and self.history_end_year is not None
            and self.history_start_year > self.history_end_year
        ):
            raise ValueError("history_start_year must be <= history_end_year")
        return self


class SingleMetricPredictionRequest(BasePredictionRequest):
    horizon_years: int = Field(gt=0)
    include_actuals: bool = True


class BacktestPredictionRequest(BasePredictionRequest):
    holdout_years: int = Field(default=3, gt=0)

    @model_validator(mode="after")
    def validate_single_backtest_country(self) -> Self:
        if len(self.country_codes) != 1:
            raise ValueError(
                "/prediction/backtest currently supports exactly one country code"
            )
        return self

    @property
    def country_code(self) -> str:
        return self.country_codes[0]


class PredictionComparisonOptions(StrictBaseModel):
    top_n: int | None = Field(default=None, gt=0)

    def to_service_options(self) -> dict[str, object]:
        return self.model_dump(exclude_none=True)


class BasePredictedComparisonRequest(StrictBaseModel):
    country_codes: list[str] = Field(min_length=1)
    horizon_years: int = Field(gt=0)
    forecast_year: int | None = None
    forecast_horizon: int | None = Field(default=None, gt=0)
    method: PredictionMethod | None = PredictionMethod.LINEAR_TREND
    fallback_method: PredictionMethod | None = PredictionMethod.LAST_OBSERVED
    comparison_options: PredictionComparisonOptions | None = None

    @field_validator("country_codes")
    @classmethod
    def normalize_country_codes(cls, values: list[str]) -> list[str]:
        return BasePredictionRequest.normalize_country_codes(values)

    @model_validator(mode="after")
    def validate_forecast_selection(self) -> Self:
        if self.forecast_year is not None and self.forecast_horizon is not None:
            raise ValueError(
                "Provide only one of forecast_year or forecast_horizon, not both"
            )
        return self


class PredictedSingleMetricComparisonRequest(BasePredictedComparisonRequest):
    metric_id: str = Field(min_length=1)

    @field_validator("metric_id")
    @classmethod
    def normalize_metric_id(cls, value: str) -> str:
        return BasePredictionRequest.normalize_metric_id(value)


class PredictedProfileComparisonRequest(BasePredictedComparisonRequest):
    profile_name: str = Field(min_length=1)

    @field_validator("profile_name")
    @classmethod
    def normalize_profile_name(cls, value: str) -> str:
        profile_name = str(value).strip()
        if not profile_name:
            raise ValueError("profile_name must be provided")
        return profile_name
