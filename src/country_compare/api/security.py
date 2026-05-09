from __future__ import annotations

import hmac
from collections.abc import Awaitable, Callable, Iterable

from fastapi import Request, status
from fastapi.responses import JSONResponse, Response

from country_compare.api.schemas.common import ErrorDetail, ErrorResponse

Handler = Callable[[Request], Awaitable[Response]]

_PROTECTED_PREFIXES: tuple[str, ...] = ("/api/v1", "/ready")
_PUBLIC_PATHS: tuple[str, ...] = (
    "/health",
    "/docs",
    "/redoc",
    "/openapi.json",
)


def api_key_required(
    path: str, protected_prefixes: Iterable[str] = _PROTECTED_PREFIXES
) -> bool:
    if path in _PUBLIC_PATHS or path.startswith("/docs/") or path.startswith("/redoc/"):
        return False
    return any(
        path == prefix or path.startswith(f"{prefix}/") for prefix in protected_prefixes
    )


async def enforce_optional_api_key(request: Request, call_next: Handler) -> Response:
    api_settings = getattr(request.app.state, "api_settings", None)
    expected_key = getattr(api_settings, "api_key", None)
    if not expected_key or not api_key_required(request.url.path):
        return await call_next(request)

    provided_key = _provided_api_key(request)
    if provided_key is not None and hmac.compare_digest(
        provided_key, str(expected_key)
    ):
        return await call_next(request)

    error = ErrorResponse(
        error=ErrorDetail(
            code="authentication_required",
            message="Provide a valid API key to access this endpoint.",
            details={"title": "Authentication required"},
        )
    )
    return JSONResponse(
        status_code=status.HTTP_401_UNAUTHORIZED,
        content=error.model_dump(mode="json"),
        headers={"WWW-Authenticate": "Bearer"},
    )


def _provided_api_key(request: Request) -> str | None:
    explicit = request.headers.get("x-api-key")
    if explicit:
        return explicit.strip()

    authorization = request.headers.get("authorization")
    if authorization and authorization.lower().startswith("bearer "):
        return authorization[7:].strip()

    return None
