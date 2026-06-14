from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

RefreshStatus = Literal[
    "completed",
    "completed_no_changes",
    "failed_retryable",
    "failed_non_retryable",
    "dry_run_completed",
]


class RefreshResult(BaseModel):
    """Terminal result returned by the shared refresh runner."""

    model_config = ConfigDict(extra="forbid")

    job_id: str
    command_id: str
    source_family: str
    status: RefreshStatus
    dataset_version: str | None = None
    artifact_uri: str | None = None
    validation_report_uri: str | None = None
    diff_report_uri: str | None = None
    row_count: int | None = Field(default=None, ge=0)
    country_count: int | None = Field(default=None, ge=0)
    metric_count: int | None = Field(default=None, ge=0)
    year_min: int | None = None
    year_max: int | None = None
    warnings: list[str] = Field(default_factory=list)
    error_code: str | None = None
    error_message: str | None = None

    @property
    def ok(self) -> bool:
        return self.status in {"completed", "completed_no_changes", "dry_run_completed"}
