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
