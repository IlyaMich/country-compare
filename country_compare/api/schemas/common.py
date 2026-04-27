from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from country_compare.services.errors import AppError


class StrictBaseModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class TablePayload(StrictBaseModel):
    """JSON-safe tabular payload exposed at the HTTP boundary."""

    row_count: int
    column_count: int
    columns: list[str]
    records: list[dict[str, Any]] = Field(default_factory=list)
    records_truncated: bool = False


class ErrorDetail(StrictBaseModel):
    code: str
    message: str
    details: dict[str, Any] = Field(default_factory=dict)

    @classmethod
    def from_app_error(cls, error: AppError) -> ErrorDetail:
        details: dict[str, Any] = {"title": error.title}

        if error.technical_detail:
            details["technical_detail"] = error.technical_detail
        if error.field_errors:
            details["field_errors"] = dict(error.field_errors)

        return cls(
            code=error.code,
            message=error.user_message,
            details=details,
        )


class ErrorResponse(StrictBaseModel):
    error: ErrorDetail


class ResultEnvelope(StrictBaseModel):
    """Common computation response envelope for future API routes.

    Phase 2 only defines and tests the transport shape. Metadata,
    comparison, scoring, and prediction routes will start returning this
    envelope in later phases.
    """

    ok: bool
    mode: str | None = None
    request: dict[str, Any] = Field(default_factory=dict)
    summary: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)
    diagnostics: dict[str, Any] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
    messages: list[Any] = Field(default_factory=list)
    tables: dict[str, TablePayload] = Field(default_factory=dict)
    charts: dict[str, Any] = Field(default_factory=dict)
    error: ErrorDetail | None = None
