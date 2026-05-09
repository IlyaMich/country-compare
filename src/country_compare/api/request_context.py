from __future__ import annotations

import contextvars
import json
import logging
import time
import uuid
from collections.abc import Callable
from typing import Any

from fastapi import Request, Response

REQUEST_ID_HEADER = "X-Request-ID"

_request_id_var: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "country_compare_request_id",
    default=None,
)


def get_request_id() -> str | None:
    """Return the request id bound to the current context, if any."""

    return _request_id_var.get()


def _new_request_id() -> str:
    return uuid.uuid4().hex


def _normalize_request_id(value: str | None) -> str:
    if value is None:
        return _new_request_id()
    stripped = value.strip()
    return stripped or _new_request_id()


async def request_context_middleware(
    request: Request,
    call_next: Callable[[Request], Any],
) -> Response:
    """Attach request ids and emit one structured access log per request."""

    request_id = _normalize_request_id(request.headers.get(REQUEST_ID_HEADER))
    request.state.request_id = request_id
    token = _request_id_var.set(request_id)
    started = time.perf_counter()
    status_code = 500

    try:
        response = await call_next(request)
        status_code = int(response.status_code)
        return response
    finally:
        duration_ms = round((time.perf_counter() - started) * 1000, 3)
        _log_access(
            request_id=request_id,
            method=request.method,
            path=request.url.path,
            status_code=status_code,
            duration_ms=duration_ms,
        )
        try:
            response.headers[REQUEST_ID_HEADER] = request_id
        except UnboundLocalError:
            pass
        _request_id_var.reset(token)


def _log_access(
    *,
    request_id: str,
    method: str,
    path: str,
    status_code: int,
    duration_ms: float,
) -> None:
    logging.getLogger("country_compare.api.access").info(
        "api.request",
        extra={
            "request_id": request_id,
            "method": method,
            "path": path,
            "status_code": status_code,
            "duration_ms": duration_ms,
        },
    )


class JsonLogFormatter(logging.Formatter):
    """Small JSON formatter for API logs without adding a logging dependency."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "timestamp": self.formatTime(record, self.datefmt),
        }
        for name in ("request_id", "method", "path", "status_code", "duration_ms"):
            value = getattr(record, name, None)
            if value is not None:
                payload[name] = value
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False, sort_keys=True)


def configure_api_logging(*, level: str = "INFO") -> None:
    """Configure API loggers for structured stdout-friendly records."""

    normalized_level = getattr(logging, level.upper(), logging.INFO)
    handler = logging.StreamHandler()
    handler.setFormatter(JsonLogFormatter())

    for logger_name in ("country_compare.api", "country_compare.api.access"):
        logger = logging.getLogger(logger_name)
        logger.handlers.clear()
        logger.addHandler(handler)
        logger.setLevel(normalized_level)
        logger.propagate = False
