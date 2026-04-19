from __future__ import annotations

from enum import Enum
from typing import Dict, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class MissingDataPolicy(str, Enum):
    RENORMALIZE_WEIGHTS = "renormalize_weights"
    DROP_COUNTRY = "drop_country"


class YearStrategy(str, Enum):
    LATEST_PER_METRIC = "latest_per_metric"
    TARGET_YEAR = "target_year"
    COMMON_YEAR = "common_year"


class NormalizationMethod(str, Enum):
    MINMAX = "minmax"
    PERCENTILE = "percentile"
    RANK = "rank"
    LOG_MINMAX = "log-minmax"


class WeightHandlingStrategy(str, Enum):
    NORMALIZE = "normalize"
    REQUIRE_SUM_TO_ONE = "require_sum_to_one"


class MetricConfig(BaseModel):
    """
    Defines how a metric should behave in comparisons and scoring.
    """

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    display_name: str
    category: str
    higher_is_better: bool
    default_weight: float = Field(gt=0)
    description: Optional[str] = None
    unit: Optional[str] = None
    source: Optional[str] = None
    normalization_method: NormalizationMethod = NormalizationMethod.MINMAX

    @field_validator("display_name", "category")
    @classmethod
    def validate_non_empty_strings(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("must not be empty")
        return value


class MetricsConfig(BaseModel):
    """
    Container for all metric definitions.
    Keys are canonical metric_id values.
    """

    model_config = ConfigDict(extra="forbid")

    metrics: Dict[str, MetricConfig]

    @field_validator("metrics")
    @classmethod
    def validate_metrics_not_empty(cls, value: Dict[str, MetricConfig]) -> Dict[str, MetricConfig]:
        if not value:
            raise ValueError("metrics config must define at least one metric")
        return value

    @field_validator("metrics")
    @classmethod
    def validate_metric_ids(cls, value: Dict[str, MetricConfig]) -> Dict[str, MetricConfig]:
        for metric_id in value:
            if not metric_id:
                raise ValueError("metric_id must not be empty")
            normalized = metric_id.strip()
            if normalized != metric_id:
                raise ValueError(f"metric_id '{metric_id}' must not contain leading/trailing whitespace")
            if " " in metric_id:
                raise ValueError(f"metric_id '{metric_id}' must not contain spaces")
        return value


class ScoringProfile(BaseModel):
    """
    Profile that chooses metrics and optionally overrides normalization,
    weights, year selection, and missing-data behavior.
    """

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    metrics: list[str] = Field(min_length=1)
    weights: Dict[str, float] = Field(default_factory=dict)
    normalization_overrides: Dict[str, NormalizationMethod] = Field(default_factory=dict)
    year_strategy: Optional[YearStrategy] = None
    missing_data_policy: Optional[MissingDataPolicy] = None
    description: Optional[str] = None

    @field_validator("metrics")
    @classmethod
    def validate_metrics_unique(cls, value: list[str]) -> list[str]:
        if len(set(value)) != len(value):
            raise ValueError("profile metrics must be unique")
        return value


    @field_validator("metrics")
    @classmethod
    def validate_metric_names(cls, value: list[str]) -> list[str]:
        for metric_id in value:
            if not metric_id.strip():
                raise ValueError("profile metric_id must not be empty")
        return value


    @field_validator("weights")
    @classmethod
    def validate_weights_positive(cls, value: Dict[str, float]) -> Dict[str, float]:
        for metric_id, weight in value.items():
            if weight <= 0:
                raise ValueError(f"weight for metric '{metric_id}' must be > 0")
        return value


class ScoringConfig(BaseModel):
    """
    Profile that chooses metrics and optionally overrides normalization,
    weights, year selection, and missing-data behavior.
    """

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    default_profile: str
    weight_handling: WeightHandlingStrategy = WeightHandlingStrategy.NORMALIZE
    default_year_strategy: YearStrategy = YearStrategy.LATEST_PER_METRIC
    default_missing_data_policy: MissingDataPolicy = MissingDataPolicy.RENORMALIZE_WEIGHTS
    profiles: Dict[str, ScoringProfile]

    @field_validator("profiles")
    @classmethod
    def validate_profiles_not_empty(cls, value: Dict[str, ScoringProfile]) -> Dict[str, ScoringProfile]:
        if not value:
            raise ValueError("must define at least one scoring profile")
        return value

    @model_validator(mode="after")
    def validate_default_profile_exists(self) -> "ScoringConfig":
        if self.default_profile not in self.profiles:
            raise ValueError(
                f"default_profile '{self.default_profile}' is not defined in profiles"
            )
        return self


class ConfigurationBundle(BaseModel):
    """
    Convenience model for passing all config together.
    """

    model_config = ConfigDict(extra="forbid")

    metrics: MetricsConfig
    scoring: ScoringConfig