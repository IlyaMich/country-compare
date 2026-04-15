from __future__ import annotations

import math
from collections.abc import Iterable

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    HttpUrl,
    field_validator,
    model_validator,
)


class MetricMetadata(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    metric_id: str = Field(..., min_length=1)
    metric_name: str = Field(..., min_length=1)
    category: str = Field(..., min_length=1)
    unit: str = Field(..., min_length=1)
    higher_is_better: bool
    source_name: str | None = None
    source_url: HttpUrl | None = None
    dataset_version: str | None = None

    @field_validator("metric_id")
    @classmethod
    def validate_metric_id(cls, value: str) -> str:
        value = value.strip()
        if " " in value:
            raise ValueError("metric_id must not contain spaces; use snake_case.")
        return value


class MetricRecord(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    country_code: str = Field(..., min_length=3, max_length=3)
    country_name: str = Field(..., min_length=1)
    metric_id: str = Field(..., min_length=1)
    metric_name: str = Field(..., min_length=1)
    value: float
    year: int
    unit: str = Field(..., min_length=1)
    source_name: str = Field(..., min_length=1)
    source_url: HttpUrl
    higher_is_better: bool
    category: str = Field(..., min_length=1)

    dataset_version: str | None = None
    region: str | None = None
    income_group: str | None = None
    notes: str | None = None

    @field_validator("country_code")
    @classmethod
    def validate_country_code(cls, value: str) -> str:
        code = value.strip().upper()
        if len(code) != 3 or not code.isalpha():
            raise ValueError("country_code must be a 3-letter ISO alpha-3 code.")
        return code

    @field_validator("metric_id")
    @classmethod
    def validate_metric_id(cls, value: str) -> str:
        value = value.strip()
        if " " in value:
            raise ValueError("metric_id must not contain spaces; use snake_case.")
        return value

    @field_validator("year")
    @classmethod
    def validate_year(cls, value: int) -> int:
        if value < 1900 or value > 2100:
            raise ValueError("year must be between 1900 and 2100.")
        return value

    @field_validator("value")
    @classmethod
    def validate_value(cls, value: float) -> float:
        if math.isnan(value) or math.isinf(value):
            raise ValueError("value must be finite.")
        return value


class MetricDataset(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    records: list[MetricRecord]

    @model_validator(mode="after")
    def validate_unique_primary_key(self) -> MetricDataset:
        seen: set[tuple[str, str, int]] = set()
        for record in self.records:
            key = (record.country_code, record.metric_id, record.year)
            if key in seen:
                raise ValueError(
                    f"Duplicate record detected for country_code={record.country_code}, "
                    f"metric_id={record.metric_id}, year={record.year}."
                )
            seen.add(key)
        return self

    @classmethod
    def from_records(cls, records: Iterable[MetricRecord]) -> MetricDataset:
        return cls(records=list(records))
