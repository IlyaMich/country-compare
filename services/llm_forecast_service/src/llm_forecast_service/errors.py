from __future__ import annotations

import logging
from collections.abc import Mapping, Sequence
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from llm_forecast_service import metrics

logger = logging.getLogger(__name__)
_MAX_DETAIL_STRING_LENGTH = 500
_ALLOWED_VALIDATION_ERROR_KEYS = {"loc", "msg", "type", "url"}


class ServiceError(Exception):
    def __init__(
        self,
        code: str,
        message: str,
        *,
        status_code: int = 400,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code
        self.details = details or {}


def _request_id_from(request: Request) -> str | None:
    request_id = getattr(request.state, "request_id", None)
    if isinstance(request_id, str) and request_id:
        return request_id
    return None


def _truncate_string(value: str) -> str:
    if len(value) <= _MAX_DETAIL_STRING_LENGTH:
        return value
    return f"{value[:_MAX_DETAIL_STRING_LENGTH]}..."


def sanitize_detail(value: Any) -> Any:
    if isinstance(value, str):
        return _truncate_string(value)
    if isinstance(value, Mapping):
        sanitized: dict[str, Any] = {}
        for key, nested in value.items():
            key_text = str(key)
            if key_text in {"input", "ctx"}:
                continue
            sanitized[key_text] = sanitize_detail(nested)
        return sanitized
    if isinstance(value, list):
        return [sanitize_detail(item) for item in value]
    if isinstance(value, tuple):
        return [sanitize_detail(item) for item in value]
    if isinstance(value, (int, float, bool)) or value is None:
        return value
    return _truncate_string(str(value))


def _sanitize_validation_errors(errors: Sequence[Any]) -> list[dict[str, Any]]:
    sanitized: list[dict[str, Any]] = []

    for error in errors:
        if not isinstance(error, Mapping):
            sanitized.append(
                {
                    "type": type(error).__name__,
                    "msg": sanitize_detail(error),
                }
            )
            continue

        sanitized_error: dict[str, Any] = {}
        for key, value in error.items():
            key_text = str(key)
            if key_text in _ALLOWED_VALIDATION_ERROR_KEYS:
                sanitized_error[key_text] = sanitize_detail(value)

        sanitized.append(sanitized_error)

    return sanitized


def error_response(
    code: str,
    message: str,
    *,
    status_code: int,
    details: dict[str, Any] | None = None,
    request_id: str | None = None,
) -> JSONResponse:
    error_details = sanitize_detail(details or {})
    if request_id:
        error_details["request_id"] = request_id
    return JSONResponse(
        status_code=status_code,
        content={
            "error": {
                "code": code,
                "message": message,
                "details": error_details,
            }
        },
    )


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(ServiceError)
    async def handle_service_error(request: Request, exc: ServiceError) -> JSONResponse:
        return error_response(
            exc.code,
            exc.message,
            status_code=exc.status_code,
            details=exc.details,
            request_id=_request_id_from(request),
        )

    @app.exception_handler(RequestValidationError)
    async def request_validation_exception_handler(
        request: Request,
        exc: RequestValidationError,
    ) -> JSONResponse:
        metrics.record_validation_failure(code="invalid_request")
        request_id = getattr(request.state, "request_id", None)

        return error_response(
            code="invalid_request",
            message="Request validation failed.",
            status_code=422,
            request_id=request_id,
            details={"errors": _sanitize_validation_errors(exc.errors())},
        )

    @app.exception_handler(ValidationError)
    async def pydantic_validation_exception_handler(
        request: Request,
        exc: ValidationError,
    ) -> JSONResponse:
        metrics.record_validation_failure(code="llm_response_invalid")
        request_id = getattr(request.state, "request_id", None)

        return error_response(
            code="llm_response_invalid",
            message="Provider response validation failed.",
            status_code=502,
            request_id=request_id,
            details={"errors": _sanitize_validation_errors(exc.errors())},
        )

    @app.exception_handler(Exception)
    async def handle_unexpected_error(request: Request, exc: Exception) -> JSONResponse:
        logger.exception(
            "unexpected_llm_forecast_service_error request_id=%s",
            _request_id_from(request) or "",
        )
        return error_response(
            "internal_error",
            "An unexpected error occurred.",
            status_code=500,
            details={},
            request_id=_request_id_from(request),
        )
