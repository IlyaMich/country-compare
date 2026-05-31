from __future__ import annotations

import math
from typing import Any

from pydantic import BaseModel, Field, field_validator, model_validator


class TimeSeriesPoint(BaseModel):
    year: int
    value: float

    @field_validator("value")
    @classmethod
    def value_must_be_finite(cls, value: float) -> float:
        if not math.isfinite(value):
            raise ValueError("value must be finite")
        return value


class ForecastConstraints(BaseModel):
    max_adjustment_pct: float = Field(gt=0)
    horizon_years: int = Field(ge=1)
    allowed_years: list[int] = Field(min_length=1)

    @field_validator("max_adjustment_pct")
    @classmethod
    def max_adjustment_must_be_finite(cls, value: float) -> float:
        if not math.isfinite(value):
            raise ValueError("max_adjustment_pct must be finite")
        return value

    @model_validator(mode="after")
    def allowed_years_must_match_horizon(self) -> ForecastConstraints:
        if len(self.allowed_years) != self.horizon_years:
            raise ValueError("allowed_years length must equal horizon_years")
        if len(set(self.allowed_years)) != len(self.allowed_years):
            raise ValueError("allowed_years must not contain duplicates")
        return self


class ForecastAdjustmentRequest(BaseModel):
    request_id: str = Field(min_length=1, max_length=200)
    country_code: str = Field(min_length=1, max_length=20)
    country_name: str = Field(min_length=1, max_length=200)
    metric_id: str = Field(min_length=1, max_length=200)
    metric_name: str = Field(min_length=1, max_length=300)
    unit: str | None = Field(default=None, max_length=100)
    history: list[TimeSeriesPoint] = Field(min_length=1)
    baseline_forecast: list[TimeSeriesPoint] = Field(min_length=1)
    constraints: ForecastConstraints
    prompt_version: str = Field(
        default="llm_forecast_mistral_v1", min_length=1, max_length=100
    )

    @model_validator(mode="after")
    def baseline_must_match_allowed_years(self) -> ForecastAdjustmentRequest:
        baseline_years = [point.year for point in self.baseline_forecast]
        if len(set(baseline_years)) != len(baseline_years):
            raise ValueError("baseline_forecast years must not contain duplicates")
        if baseline_years != self.constraints.allowed_years:
            raise ValueError("baseline_forecast years must exactly match allowed_years")
        return self


class ForecastAdjustmentOutput(BaseModel):
    forecast_points: list[TimeSeriesPoint] = Field(min_length=1)
    rationale: str = Field(default="", max_length=2_000)
    assumptions: list[str] = Field(default_factory=list, max_length=5)
    warnings: list[str] = Field(default_factory=list, max_length=5)

    @field_validator("assumptions", "warnings")
    @classmethod
    def provider_text_lists_are_bounded(cls, values: list[str]) -> list[str]:
        for value in values:
            if len(value) > 500:
                raise ValueError(
                    "provider text list entries must be at most 500 characters"
                )
        return values


class ForecastAdjustmentResponse(ForecastAdjustmentOutput):
    metadata: dict[str, Any] = Field(default_factory=dict)


class CapabilitiesResponse(BaseModel):
    provider: str
    model: str
    supports_structured_output: bool
    supports_bounded_adjustment: bool
    max_series_per_request: int
    max_horizon_years: int
    max_history_points: int
    one_call_per_series: bool
    zdr_required: bool
    zdr_confirmed: bool


class HealthResponse(BaseModel):
    status: str
    service: str


class ReadyResponse(BaseModel):
    status: str
    provider: str | None = None
    model: str | None = None
    deployment_profile: str
    zdr_required: bool
    zdr_confirmed: bool
    issues: list[str] = Field(default_factory=list)


class ErrorBody(BaseModel):
    code: str
    message: str
    details: dict[str, Any] = Field(default_factory=dict)


class ErrorResponse(BaseModel):
    error: ErrorBody
