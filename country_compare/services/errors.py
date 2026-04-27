from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field

from pydantic import ValidationError

from country_compare.config.validator import ConfigurationValidationError


@dataclass(frozen=True)
class AppError:
    code: str
    title: str
    user_message: str
    technical_detail: str | None = None
    field_errors: Mapping[str, str] = field(default_factory=dict)


class AppServiceError(Exception):
    """Exception wrapper carrying an app-facing error payload."""

    def __init__(self, error: AppError) -> None:
        self.error = error
        super().__init__(error.user_message)


def error_from_exception(
    exc: Exception,
    *,
    default_code: str = "unexpected_error",
    default_title: str = "Unexpected error",
    default_user_message: str = "Something went wrong while processing the request.",
) -> AppError:
    if isinstance(exc, AppServiceError):
        return exc.error

    if isinstance(exc, FileNotFoundError):
        return AppError(
            code="resource_not_found",
            title="Resource not found",
            user_message="A required file could not be found.",
            technical_detail=str(exc),
        )

    if isinstance(exc, ConfigurationValidationError):
        return AppError(
            code="config_invalid",
            title="Invalid configuration",
            user_message="The configuration files loaded, but they are internally inconsistent.",
            technical_detail=str(exc),
        )

    if isinstance(exc, ValidationError):
        return AppError(
            code="validation_failed",
            title="Validation failed",
            user_message="One of the project models rejected the provided data.",
            technical_detail=str(exc),
        )

    if isinstance(exc, ValueError):
        return AppError(
            code="input_invalid",
            title="Invalid input",
            user_message="A value or project setting is invalid for this operation.",
            technical_detail=str(exc),
        )

    return AppError(
        code=default_code,
        title=default_title,
        user_message=default_user_message,
        technical_detail=str(exc),
    )
