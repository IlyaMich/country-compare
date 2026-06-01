from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class CategorySummaryResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    row_count: int
    country_count: int
    metric_count: int


class DatasetMetadataResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    exists: bool
    backend: str
    dataset_path: str | None = None
    row_count: int = 0
    country_count: int = 0
    metric_count: int = 0
    year_min: int | None = None
    year_max: int | None = None
    available_columns: list[str] = Field(default_factory=list)
    categories: list[CategorySummaryResponse] = Field(default_factory=list)
    dataset_versions: list[str] = Field(default_factory=list)
    dataset_checksum: str | None = None
    dataset_size_bytes: int | None = None
    dataset_modified_at: str | None = None
    schema_valid: bool | None = None
    schema_issue_count: int = 0
    schema_issues: list[str] = Field(default_factory=list)


class CountryOptionResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str
    name: str


class CountriesMetadataResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    countries: list[CountryOptionResponse]


class MetricOptionResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    metric_id: str
    display_name: str
    category: str | None = None
    unit: str | None = None


class MetricsMetadataResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    metrics: list[MetricOptionResponse]


class YearsMetadataResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    years: list[int]
    min_year: int | None = None
    max_year: int | None = None


class ProfileOptionResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    profile_name: str
    description: str | None = None
    metric_ids: list[str] = Field(default_factory=list)
    metric_count: int
    year_strategy: str | None = None
    missing_data_policy: str | None = None


class ProfilesMetadataResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    profiles: list[ProfileOptionResponse]


class PredictionMethodResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    method_id: str
    display_name: str
    description: str
    metadata: dict[str, object] = Field(default_factory=dict)


class PredictionMethodsMetadataResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    methods: list[PredictionMethodResponse]
