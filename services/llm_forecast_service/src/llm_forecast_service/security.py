from __future__ import annotations

import hmac

from fastapi import Request
from fastapi.security.utils import get_authorization_scheme_param

from llm_forecast_service.errors import ServiceError
from llm_forecast_service.settings import ServiceSettings


def verify_bearer_token(authorization: str | None, settings: ServiceSettings) -> None:
    scheme, token = get_authorization_scheme_param(authorization)
    if not authorization or scheme.lower() != "bearer" or not token:
        raise ServiceError(
            "unauthorized",
            "Missing bearer token.",
            status_code=401,
        )
    if not settings.service_token:
        raise ServiceError(
            "service_not_configured",
            "LLM service token is not configured.",
            status_code=503,
        )
    if not hmac.compare_digest(token, settings.service_token):
        raise ServiceError(
            "unauthorized",
            "Invalid bearer token.",
            status_code=401,
        )


def require_service_token(request: Request) -> None:
    settings = request.app.state.settings
    verify_bearer_token(request.headers.get("Authorization"), settings)
