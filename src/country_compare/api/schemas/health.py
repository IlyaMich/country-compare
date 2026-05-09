from __future__ import annotations

from typing import Literal

from pydantic import Field

from country_compare.api.schemas.common import StrictBaseModel


class HealthResponse(StrictBaseModel):
    status: Literal["ok"] = "ok"
    service: str = "country-compare-api"
    version: str
    api_version: str


class ReadyDatasetStatus(StrictBaseModel):
    exists: bool
    backend: str | None = None
    dataset_path: str | None = None
    row_count: int = 0
    country_count: int = 0
    metric_count: int = 0
    year_min: int | None = None
    year_max: int | None = None
    dataset_versions: list[str] = Field(default_factory=list)
    dataset_checksum: str | None = None
    dataset_size_bytes: int | None = None
    dataset_modified_at: str | None = None
    manifest_path: str | None = None
    manifest_exists: bool = False
    manifest_valid: bool | None = None
    manifest_issue_count: int = 0
    manifest_issues: list[str] = Field(default_factory=list)
    manifest_dataset_version: str | None = None
    manifest_created_at: str | None = None
    manifest_schema_version: str | None = None
    schema_valid: bool | None = None
    schema_issue_count: int = 0
    schema_issues: list[str] = Field(default_factory=list)
    error: str | None = None


class ReadyConfigStatus(StrictBaseModel):
    valid: bool
    validated_against_dataset: bool = True
    metrics_count: int = 0
    profile_count: int = 0
    messages: list[str] = Field(default_factory=list)
    error: str | None = None


class ReadyResponse(StrictBaseModel):
    status: Literal["ready", "not_ready"]
    dataset: ReadyDatasetStatus
    config: ReadyConfigStatus
    warnings: list[str] = Field(default_factory=list)
