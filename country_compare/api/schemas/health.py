from __future__ import annotations

from typing import Literal

from pydantic import Field

from country_compare.api.schemas.common import StrictBaseModel


class HealthResponse(StrictBaseModel):
    status: Literal["ok"] = "ok"
    service: str = "country-compare-api"
    version: str


class ReadyDatasetStatus(StrictBaseModel):
    exists: bool


class ReadyConfigStatus(StrictBaseModel):
    valid: bool
    validated_against_dataset: bool = True


class ReadyResponse(StrictBaseModel):
    status: Literal["ready", "not_ready"]
    dataset: ReadyDatasetStatus
    config: ReadyConfigStatus
    warnings: list[str] = Field(default_factory=list)
