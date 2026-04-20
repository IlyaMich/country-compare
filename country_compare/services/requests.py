from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from country_compare.config.models import YearStrategy

ComparisonMode = Literal["single_metric", "multi_metric", "weighted_score"]


def _normalize_codes(values: list[str]) -> list[str]:
    normalized: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = str(value).strip().upper()
        if not text or text in seen:
            continue
        normalized.append(text)
        seen.add(text)
    return normalized


def _normalize_strings(values: list[str]) -> list[str]:
    normalized: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = str(value).strip()
        if not text or text in seen:
            continue
        normalized.append(text)
        seen.add(text)
    return normalized


@dataclass(slots=True)
class BaseComparisonRequest:
    countries: list[str]
    year_strategy: YearStrategy | str = YearStrategy.LATEST_PER_METRIC
    target_year: int | None = None
    top_n: int | None = None

    def __post_init__(self) -> None:
        self.countries = _normalize_codes(self.countries)
        self.year_strategy = YearStrategy(self.year_strategy)
        if self.top_n is not None:
            self.top_n = int(self.top_n)
            if self.top_n <= 0:
                raise ValueError("top_n must be positive when provided")
        if self.year_strategy == YearStrategy.TARGET_YEAR:
            if self.target_year is None:
                raise ValueError("target_year is required when year_strategy='target_year'")
            self.target_year = int(self.target_year)
        elif self.target_year is not None:
            self.target_year = int(self.target_year)


@dataclass(slots=True)
class SingleMetricRequest(BaseComparisonRequest):
    metric_id: str = ""
    mode: ComparisonMode = field(init=False, default="single_metric")

    def __post_init__(self) -> None:
        BaseComparisonRequest.__post_init__(self)
        self.metric_id = str(self.metric_id).strip()
        if not self.metric_id:
            raise ValueError("metric_id must be provided")


@dataclass(slots=True)
class MultiMetricRequest(BaseComparisonRequest):
    metric_ids: list[str] = field(default_factory=list)
    mode: ComparisonMode = field(init=False, default="multi_metric")

    def __post_init__(self) -> None:
        BaseComparisonRequest.__post_init__(self)
        self.metric_ids = _normalize_strings(self.metric_ids)
        if not self.metric_ids:
            raise ValueError("metric_ids must contain at least one metric")


@dataclass(slots=True)
class WeightedScoreRequest(BaseComparisonRequest):
    profile_name: str = ""
    mode: ComparisonMode = field(init=False, default="weighted_score")

    def __post_init__(self) -> None:
        BaseComparisonRequest.__post_init__(self)
        self.profile_name = str(self.profile_name).strip()
        if not self.profile_name:
            raise ValueError("profile_name must be provided")