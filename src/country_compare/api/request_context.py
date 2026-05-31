from __future__ import annotations

import contextvars
import json
import logging
import time
import uuid
from collections.abc import Callable
from typing import Any

from fastapi import Request, Response

from country_compare.api.metrics import metrics_registry, normalize_route_path

_API_LOG_HANDLER_ATTR = "_country_compare_api_handler"

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
    """Attach request ids, emit structured access logs, and record metrics."""

    request_id = _normalize_request_id(request.headers.get(REQUEST_ID_HEADER))
    request.state.request_id = request_id
    token = _request_id_var.set(request_id)
    started = time.perf_counter()
    status_code = 500
    response: Response | None = None

    try:
        response = await call_next(request)
        status_code = int(response.status_code)
        return response
    finally:
        duration_seconds = time.perf_counter() - started
        duration_ms = round(duration_seconds * 1000, 3)
        path_label = normalize_route_path(request)

        metrics_registry.record_request(
            method=request.method,
            path=path_label,
            status_code=status_code,
            duration_seconds=duration_seconds,
        )
        _log_access(
            request_id=request_id,
            method=request.method,
            path=path_label,
            status_code=status_code,
            duration_ms=duration_ms,
        )

        if response is not None:
            response.headers[REQUEST_ID_HEADER] = request_id
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

        for name in (
            "request_id",
            "method",
            "path",
            "status_code",
            "duration_ms",
            "reason",
            "runtime_env",
            "auth_enabled",
            "auth_required",
            "docs_enabled",
            "metrics_enabled",
        ):
            value = getattr(record, name, None)
            if value is not None:
                payload[name] = value

        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)

        return json.dumps(payload, ensure_ascii=False, sort_keys=True)


def configure_api_logging(
    *,
    level: str = "INFO",
    log_format: str = "json",
    propagate: bool = True,
    clear_handlers: bool = False,
) -> None:
    """Configure API loggers for structured records.

    Existing non-API handlers are preserved unless ``clear_handlers`` is set.
    The API-owned stderr handler is replaced on each call so pytest capsys and
    repeated create_app() calls do not keep stale stderr streams.
    """

    normalized_level = getattr(logging, level.upper())
    formatter: logging.Formatter
    if log_format == "json":
        formatter = JsonLogFormatter()
    elif log_format == "plain":
        formatter = logging.Formatter(
            "%(asctime)s %(levelname)s %(name)s %(message)s "
            "request_id=%(request_id)s method=%(method)s path=%(path)s "
            "status=%(status_code)s duration_ms=%(duration_ms)s"
        )
    else:
        raise ValueError("log_format must be 'json' or 'plain'.")

    logger_names = (
        "country_compare.api",
        "country_compare.api.access",
        "country_compare.api.security",
    )

    for logger_name in logger_names:
        logger = logging.getLogger(logger_name)
        if clear_handlers:
            logger.handlers.clear()
        else:
            logger.handlers[:] = [
                handler
                for handler in logger.handlers
                if not getattr(handler, _API_LOG_HANDLER_ATTR, False)
            ]

        logger.setLevel(normalized_level)
        logger.propagate = propagate

    handler = logging.StreamHandler()
    setattr(handler, _API_LOG_HANDLER_ATTR, True)
    handler.setFormatter(formatter)

    logging.getLogger("country_compare.api").addHandler(handler)
