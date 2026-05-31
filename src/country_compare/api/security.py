from __future__ import annotations

import hmac
import logging
from collections.abc import Awaitable, Callable, Iterable

from fastapi import Request, status
from fastapi.responses import JSONResponse, Response

from country_compare.api.metrics import metrics_registry
from country_compare.api.request_context import get_request_id
from country_compare.api.settings import ApiSettings

Handler = Callable[[Request], Awaitable[Response]]

LOGGER = logging.getLogger("country_compare.api.security")

_DEFAULT_PROTECTED_PREFIXES: tuple[str, ...] = ("/api/v1", "/ready")
_DEFAULT_PUBLIC_PATHS: tuple[str, ...] = ("/health", "/docs", "/redoc", "/openapi.json")
_DOCS_PATHS: tuple[str, ...] = ("/docs", "/redoc", "/openapi.json")


def api_key_required(
    path: str,
    api_settings: ApiSettings | None = None,
    protected_prefixes: Iterable[str] | None = None,
) -> bool:
    """Return whether ``path`` should require an API key when auth is enabled."""

    settings = api_settings
    configured_protected_prefixes = tuple(
        protected_prefixes
        if protected_prefixes is not None
        else getattr(settings, "protected_prefixes", _DEFAULT_PROTECTED_PREFIXES)
    )
    public_paths = tuple(getattr(settings, "public_paths", _DEFAULT_PUBLIC_PATHS))

    if _is_docs_path(path):
        return bool(getattr(settings, "protect_docs", False))

    if path == "/metrics":
        return bool(getattr(settings, "protect_metrics", True))

    if path in public_paths:
        return False

    return any(
        path == prefix or path.startswith(f"{prefix}/")
        for prefix in configured_protected_prefixes
    )


async def enforce_optional_api_key(request: Request, call_next: Handler) -> Response:
    api_settings = getattr(request.app.state, "api_settings", None)
    expected_key = getattr(api_settings, "api_key", None)
    should_protect = api_key_required(request.url.path, api_settings=api_settings)

    if not should_protect:
        return await call_next(request)

    if not expected_key:
        LOGGER.warning(
            "api.auth_disabled",
            extra={
                "request_id": get_request_id(),
                "method": request.method,
                "path": request.url.path,
                "status_code": status.HTTP_200_OK,
                "reason": "api_key_unset",
            },
        )
        return await call_next(request)

    provided_key = _provided_api_key(request)
    if provided_key is not None and hmac.compare_digest(
        provided_key, str(expected_key)
    ):
        LOGGER.debug(
            "api.auth_success",
            extra={
                "request_id": get_request_id(),
                "method": request.method,
                "path": request.url.path,
                "status_code": status.HTTP_200_OK,
            },
        )
        return await call_next(request)

    reason = "missing_api_key" if provided_key is None else "invalid_api_key"
    _log_auth_failure(request=request, reason=reason)
    metrics_registry.record_auth_failure(reason=reason)

    return JSONResponse(
        status_code=status.HTTP_401_UNAUTHORIZED,
        content={
            "error": {
                "code": "authentication_required",
                "message": "Provide a valid API key to access this endpoint.",
                "details": {"title": "Authentication required"},
            }
        },
        headers={"WWW-Authenticate": "Bearer"},
    )


def _is_docs_path(path: str) -> bool:
    return (
        path in _DOCS_PATHS or path.startswith("/docs/") or path.startswith("/redoc/")
    )


def _provided_api_key(request: Request) -> str | None:
    explicit = request.headers.get("x-api-key")
    if explicit:
        return explicit.strip()

    authorization = request.headers.get("authorization")
    if authorization and authorization.lower().startswith("bearer "):
        return authorization[7:].strip()

    return None


def _log_auth_failure(*, request: Request, reason: str) -> None:
    LOGGER.warning(
        "api.auth_failure",
        extra={
            "request_id": get_request_id(),
            "method": request.method,
            "path": request.url.path,
            "status_code": status.HTTP_401_UNAUTHORIZED,
            "reason": reason,
        },
    )
