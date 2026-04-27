from __future__ import annotations

from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse

from country_compare.api.schemas.common import ErrorDetail, ErrorResponse
from country_compare.services.errors import (
    AppError,
    AppServiceError,
    error_from_exception,
)


def register_exception_handlers(app: FastAPI) -> None:
    """Register the minimal API-level exception mapping for Phase 1."""

    @app.exception_handler(AppServiceError)
    async def handle_app_service_error(
        _request: Request, exc: AppServiceError
    ) -> JSONResponse:
        return _error_response(exc.error, status_code=_status_for_app_error(exc.error))

    @app.exception_handler(Exception)
    async def handle_unexpected_error(
        _request: Request, exc: Exception
    ) -> JSONResponse:
        error = error_from_exception(
            exc,
            default_code="unexpected_error",
            default_title="Unexpected API error",
            default_user_message="The API could not complete the request.",
        )
        return _error_response(error, status_code=_status_for_app_error(error))


def _error_response(error: AppError, *, status_code: int) -> JSONResponse:
    payload = ErrorResponse(error=ErrorDetail.from_app_error(error))
    return JSONResponse(status_code=status_code, content=payload.model_dump())


def _status_for_app_error(error: AppError) -> int:
    if error.code == "resource_not_found":
        return status.HTTP_404_NOT_FOUND
    if error.code in {"config_invalid", "dataset_invalid", "state_invalid"}:
        return status.HTTP_409_CONFLICT
    if error.code in {"input_invalid", "validation_failed"}:
        return status.HTTP_400_BAD_REQUEST

    return status.HTTP_500_INTERNAL_SERVER_ERROR
