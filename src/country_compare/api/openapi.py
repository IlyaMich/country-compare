from __future__ import annotations

from typing import Any

from fastapi import FastAPI
from fastapi.openapi.utils import get_openapi

from country_compare.api.security import api_key_required

_API_KEY_SECURITY_SCHEME = "ApiKeyAuth"
_BEARER_SECURITY_SCHEME = "BearerAuth"
_HTTP_METHODS = {"get", "put", "post", "delete", "options", "head", "patch", "trace"}

SECURITY_REQUIREMENTS: list[dict[str, list[str]]] = [
    {_API_KEY_SECURITY_SCHEME: []},
    {_BEARER_SECURITY_SCHEME: []},
]

SECURITY_SCHEMES: dict[str, dict[str, str]] = {
    _API_KEY_SECURITY_SCHEME: {
        "type": "apiKey",
        "in": "header",
        "name": "X-API-Key",
        "description": "Shared beta API key passed in the X-API-Key header.",
    },
    _BEARER_SECURITY_SCHEME: {
        "type": "http",
        "scheme": "bearer",
        "description": "Shared beta API key passed as an Authorization: Bearer token.",
    },
}


def install_openapi_security(app: FastAPI) -> None:
    """Add API-key authentication metadata to the generated OpenAPI schema.

    Runtime API-key enforcement is handled by middleware in ``security.py``.
    This hook documents the same contract for Swagger UI, ReDoc, generated
    clients, and other OpenAPI consumers without making docs endpoints private.
    """

    def custom_openapi() -> dict[str, Any]:
        if app.openapi_schema:
            return app.openapi_schema

        openapi_schema = get_openapi(
            title=app.title,
            version=app.version,
            description=app.description,
            routes=app.routes,
        )
        _add_security_schemes(openapi_schema)
        _mark_protected_operations(openapi_schema)
        app.openapi_schema = openapi_schema
        return app.openapi_schema

    app.openapi = custom_openapi  # type: ignore[method-assign]


def _add_security_schemes(openapi_schema: dict[str, Any]) -> None:
    components = openapi_schema.setdefault("components", {})
    security_schemes = components.setdefault("securitySchemes", {})
    security_schemes.update(SECURITY_SCHEMES)


def _mark_protected_operations(openapi_schema: dict[str, Any]) -> None:
    paths = openapi_schema.get("paths", {})
    if not isinstance(paths, dict):
        return

    for path, path_item in paths.items():
        if not isinstance(path, str) or not isinstance(path_item, dict):
            continue
        if not api_key_required(path):
            continue

        for method_name, operation in path_item.items():
            if method_name not in _HTTP_METHODS or not isinstance(operation, dict):
                continue
            operation.setdefault("security", SECURITY_REQUIREMENTS)
