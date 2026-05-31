from __future__ import annotations

from typing import Any, cast

from fastapi import FastAPI
from fastapi.openapi.utils import get_openapi

from country_compare.api.security import api_key_required

_API_KEY_SCHEME: dict[str, Any] = {
    "type": "apiKey",
    "in": "header",
    "name": "X-API-Key",
    "description": "Shared beta API key passed in the X-API-Key header.",
}
_BEARER_SCHEME: dict[str, Any] = {
    "type": "http",
    "scheme": "bearer",
    "description": "Shared beta API key passed as an Authorization: Bearer token.",
}


def install_openapi_security(app: FastAPI) -> None:
    """Install OpenAPI security metadata matching runtime path auth rules."""

    def custom_openapi() -> dict[str, Any]:
        if app.openapi_schema:
            return app.openapi_schema

        schema = get_openapi(
            title=app.title,
            version=app.version,
            description=app.description,
            routes=app.routes,
        )
        api_settings = getattr(app.state, "api_settings", None)

        if getattr(api_settings, "auth_enabled", False):
            components = schema.setdefault("components", {})
            security_schemes = components.setdefault("securitySchemes", {})
            security_schemes.setdefault("ApiKeyAuth", _API_KEY_SCHEME)
            security_schemes.setdefault("BearerAuth", _BEARER_SCHEME)

            for path, path_item in schema.get("paths", {}).items():
                if not api_key_required(path, api_settings=api_settings):
                    continue
                for operation in path_item.values():
                    if isinstance(operation, dict):
                        operation["security"] = [
                            {"ApiKeyAuth": []},
                            {"BearerAuth": []},
                        ]

        app.openapi_schema = schema
        return app.openapi_schema

    cast(Any, app).openapi = custom_openapi
