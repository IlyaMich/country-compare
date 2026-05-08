from __future__ import annotations

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from country_compare.api.schemas.common import ErrorDetail, ResultEnvelope
from country_compare.services.errors import (
    AppError,
    AppServiceError,
    error_from_exception,
)


# Starlette renamed HTTP_422_UNPROCESSABLE_ENTITY to
# HTTP_422_UNPROCESSABLE_CONTENT. Use the new name when available and fall
# back to the numeric value for older FastAPI/Starlette versions.
HTTP_422_UNPROCESSABLE_CONTENT = getattr(
    status, "HTTP_422_UNPROCESSABLE_CONTENT", 422
)


def register_exception_handlers(app: FastAPI) -> None:
    """Register API-level exception mapping."""

    @app.exception_handler(AppServiceError)
    async def handle_app_service_error(
        _request: Request, exc: AppServiceError
    ) -> JSONResponse:
        return _error_response(exc.error, status_code=_status_for_app_error(exc.error))

    @app.exception_handler(RequestValidationError)
    async def handle_request_validation_error(
        _request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        field_errors = {
            ".".join(str(part) for part in error.get("loc", ())): str(
                error.get("msg", "Invalid value")
            )
            for error in exc.errors()
        }
        app_error = AppError(
            code="validation_failed",
            title="Request validation failed",
            user_message="One or more request values are invalid.",
            technical_detail=str(exc),
            field_errors=field_errors,
        )
        return _error_response(
            app_error, status_code=HTTP_422_UNPROCESSABLE_CONTENT
        )

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
    payload = ResultEnvelope(ok=False, error=ErrorDetail.from_app_error(error))
    return JSONResponse(
        status_code=status_code, content=payload.model_dump(mode="json")
    )


def _status_for_app_error(error: AppError) -> int:
    if error.code == "resource_not_found":
        return status.HTTP_404_NOT_FOUND
    if error.code in {
        "configuration_invalid",
        "config_invalid",
        "dataset_invalid",
        "state_invalid",
    }:
        return status.HTTP_409_CONFLICT
    if error.code in {
        "input_invalid",
        "input_limit_exceeded",
        "selection_invalid",
        "validation_failed",
    }:
        return status.HTTP_400_BAD_REQUEST
    if error.code == "authentication_required":
        return status.HTTP_401_UNAUTHORIZED

    return status.HTTP_500_INTERNAL_SERVER_ERROR
