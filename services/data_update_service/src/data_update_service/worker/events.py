from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

from data_update_service.orchestration.commands import RefreshCommand
from data_update_service.orchestration.results import RefreshResult


class RefreshStatusEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: str = "1.0"
    event_id: str = Field(min_length=1)
    job_id: str = Field(min_length=1)
    command_id: str = Field(min_length=1)
    source_family: str = Field(min_length=1)
    status: str = Field(min_length=1)
    message: str = Field(min_length=1)
    created_at: datetime
    details: dict[str, Any] = Field(default_factory=dict)


class DeadLetterEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: str = "1.0"
    event_id: str = Field(min_length=1)
    original_topic: str = Field(min_length=1)
    original_key: str | None = None
    job_id: str | None = None
    command_id: str | None = None
    source_family: str | None = None
    error_code: str = Field(min_length=1)
    error_message: str = Field(min_length=1)
    created_at: datetime
    raw_payload: str | None = None
    command: dict[str, Any] | None = None
    result: dict[str, Any] | None = None


def make_status_event(
    *,
    command: RefreshCommand,
    status: str,
    message: str,
    details: dict[str, Any] | None = None,
) -> RefreshStatusEvent:
    return RefreshStatusEvent(
        event_id=f"evt_{uuid4().hex}",
        job_id=command.job_id,
        command_id=command.command_id,
        source_family=command.source_family,
        status=status,
        message=message,
        created_at=datetime.now(tz=UTC),
        details=details or {},
    )


def make_result_status_event(
    *,
    command: RefreshCommand,
    result: RefreshResult,
) -> RefreshStatusEvent:
    return make_status_event(
        command=command,
        status=result.status,
        message=f"Refresh job finished with status {result.status}",
        details=result.model_dump(mode="json", exclude_none=True),
    )
