from __future__ import annotations

import os
from typing import Any

from country_compare.clients.base import CountryCompareClient
from country_compare.clients.http import HttpCountryCompareClient
from country_compare.clients.local import LocalCountryCompareClient
from country_compare.services import AppContext, AppFacade

COUNTRY_COMPARE_API_URL_ENV = "COUNTRY_COMPARE_API_URL"
COUNTRY_COMPARE_API_KEY_ENV = "COUNTRY_COMPARE_API_KEY"


def resolve_api_url(value: str | None = None) -> str | None:
    raw_value = os.getenv(COUNTRY_COMPARE_API_URL_ENV) if value is None else value
    normalized = str(raw_value or "").strip().rstrip("/")
    return normalized or None


def resolve_api_key(value: str | None = None) -> str | None:
    raw_value = os.getenv(COUNTRY_COMPARE_API_KEY_ENV) if value is None else value
    normalized = str(raw_value or "").strip()
    return normalized or None


def build_country_compare_client(
    context: AppContext,
    *,
    facade: AppFacade | None = None,
    api_url: str | None = None,
    api_key: str | None = None,
    services: dict[str, Any] | None = None,
) -> CountryCompareClient:
    resolved_api_url = resolve_api_url(api_url)

    if resolved_api_url is not None:
        return HttpCountryCompareClient(
            resolved_api_url, api_key=resolve_api_key(api_key)
        )

    return LocalCountryCompareClient(
        context=context,
        facade=facade,
        services=services,
    )


__all__ = [
    "COUNTRY_COMPARE_API_URL_ENV",
    "COUNTRY_COMPARE_API_KEY_ENV",
    "CountryCompareClient",
    "HttpCountryCompareClient",
    "LocalCountryCompareClient",
    "build_country_compare_client",
    "resolve_api_key",
    "resolve_api_url",
]
