from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from country_compare.services.errors import AppError


class StrictBaseModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


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
