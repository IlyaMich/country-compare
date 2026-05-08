from __future__ import annotations

from country_compare.clients import COUNTRY_COMPARE_API_URL_ENV
from country_compare.ui import bootstrap


def test_get_ui_services_uses_local_services_when_api_url_unset(
    monkeypatch,
    fake_app_context,
) -> None:
    local_services: dict[str, object] = {"mode": "local"}

    def build_local_services(context: object) -> dict[str, object]:
        assert context is fake_app_context
        return local_services

    def fail_http_services(context: object, api_url: str) -> dict[str, object]:
        raise AssertionError(
            "HTTP UI services should not be built when COUNTRY_COMPARE_API_URL "
            "is unset."
        )

    monkeypatch.delenv(COUNTRY_COMPARE_API_URL_ENV, raising=False)
    monkeypatch.setattr(bootstrap, "_build_ui_services_cached", build_local_services)
    monkeypatch.setattr(
        bootstrap,
        "_build_http_ui_services_cached",
        fail_http_services,
    )

    assert bootstrap.get_ui_services(fake_app_context) is local_services


def test_get_ui_services_uses_http_services_when_api_url_set(
    monkeypatch,
    fake_app_context,
) -> None:
    http_services: dict[str, object] = {"mode": "http"}
    seen_api_urls: list[str] = []

    def fail_local_services(context: object) -> dict[str, object]:
        raise AssertionError(
            "Local UI services should not be built when COUNTRY_COMPARE_API_URL "
            "is set."
        )

    def build_http_services(context: object, api_url: str) -> dict[str, object]:
        assert context is fake_app_context
        seen_api_urls.append(api_url)
        return http_services

    monkeypatch.setenv(
        COUNTRY_COMPARE_API_URL_ENV,
        "  http://localhost:8000/  ",
    )
    monkeypatch.setattr(bootstrap, "_build_ui_services_cached", fail_local_services)
    monkeypatch.setattr(
        bootstrap,
        "_build_http_ui_services_cached",
        build_http_services,
    )

    assert bootstrap.get_ui_services(fake_app_context) is http_services
    assert seen_api_urls == ["http://localhost:8000"]
