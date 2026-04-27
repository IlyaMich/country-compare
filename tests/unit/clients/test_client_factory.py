from __future__ import annotations

from country_compare.clients import build_country_compare_client, resolve_api_url
from country_compare.clients.http import HttpCountryCompareClient
from country_compare.clients.local import LocalCountryCompareClient


def test_resolve_api_url_returns_none_for_blank_value() -> None:
    assert resolve_api_url("") is None
    assert resolve_api_url("   ") is None


def test_resolve_api_url_strips_configured_value() -> None:
    assert resolve_api_url("  http://localhost:8000  ") == "http://localhost:8000"


def test_build_client_defaults_to_local(fake_app_context) -> None:
    client = build_country_compare_client(fake_app_context, api_url="")

    assert isinstance(client, LocalCountryCompareClient)
    assert client.mode == "local"


def test_build_client_uses_http_when_api_url_is_set(fake_app_context) -> None:
    client = build_country_compare_client(
        fake_app_context,
        api_url="http://localhost:8000",
    )

    assert isinstance(client, HttpCountryCompareClient)
    assert client.mode == "http"
    client.close()
