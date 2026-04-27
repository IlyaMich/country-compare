from __future__ import annotations

from typing import Self

from pydantic import Field, model_validator

from country_compare.api.schemas.common import StrictBaseModel
from country_compare.config.models import YearStrategy


class BaseComparisonRequest(StrictBaseModel):
    country_codes: list[str] = Field(min_length=1)
    year_strategy: YearStrategy = YearStrategy.LATEST_PER_METRIC
    target_year: int | None = None
    top_n: int | None = Field(default=None, gt=0)

    @model_validator(mode="after")
    def validate_target_year_for_strategy(self) -> Self:
        if self.year_strategy == YearStrategy.TARGET_YEAR and self.target_year is None:
            raise ValueError("target_year is required when year_strategy='target_year'")
        return self


class SingleMetricComparisonRequest(BaseComparisonRequest):
    metric_id: str = Field(min_length=1)


class MultiMetricComparisonRequest(BaseComparisonRequest):
    metric_ids: list[str] = Field(min_length=1)


class WeightedScoreComparisonRequest(BaseComparisonRequest):
    profile_name: str = Field(min_length=1)
