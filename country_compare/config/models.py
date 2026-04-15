from __future__ import annotations

from pydantic import BaseModel

from country_compare.types import MissingDataPolicy, NormalizationMethod, YearStrategy


class MetricConfig(BaseModel):
    display_name: str
    category: str
    unit: str
    higher_is_better: bool
    default_weight: float
    normalization: NormalizationMethod


class ScoringProfile(BaseModel):
    description: str
    weights: dict[str, float]
    missing_data_policy: MissingDataPolicy
    year_strategy: YearStrategy
