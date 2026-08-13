from __future__ import annotations

from country_compare.clients import COUNTRY_COMPARE_API_URL_ENV
from country_compare.ui import bootstrap
from country_compare.ui.runtime import UiMode


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
    seen_api_keys: list[str | None] = []

    def fail_local_services(context: object) -> dict[str, object]:
        raise AssertionError(
            "Local UI services should not be built when COUNTRY_COMPARE_API_URL "
            "is set."
        )

    def build_http_services(
        context: object, api_url: str, api_key: str | None
    ) -> dict[str, object]:
        assert context is fake_app_context
        seen_api_urls.append(api_url)
        seen_api_keys.append(api_key)
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
    assert seen_api_keys == [None]


def test_get_ui_runtime_context_uses_selected_local_client(
    monkeypatch,
    fake_app_context,
) -> None:
    class FakeClient:
        mode = "local"

    client = FakeClient()

    monkeypatch.setattr(
        bootstrap,
        "get_country_compare_client",
        lambda context: client,
    )

    runtime = bootstrap.get_ui_runtime_context(fake_app_context)

    assert runtime.app_context is fake_app_context
    assert runtime.client is client
    assert runtime.mode is UiMode.LOCAL
    assert runtime.capabilities.config_editing is True


def test_get_ui_runtime_context_uses_selected_http_client(
    monkeypatch,
    fake_app_context,
) -> None:
    class FakeClient:
        mode = "http"

    client = FakeClient()

    monkeypatch.setattr(
        bootstrap,
        "get_country_compare_client",
        lambda context: client,
    )

    runtime = bootstrap.get_ui_runtime_context(fake_app_context)

    assert runtime.app_context is fake_app_context
    assert runtime.client is client
    assert runtime.mode is UiMode.HTTP
    assert runtime.capabilities.config_editing is False


def test_build_client_does_not_build_local_facade_for_http_mode(
    monkeypatch,
    fake_app_context,
) -> None:
    api_url = "https://api.example.com"

    class FakeHttpClient:
        mode = "http"

    expected_client = FakeHttpClient()

    def fail_build_facade(context):
        raise AssertionError("Local AppFacade must not be built for HTTP client mode.")

    def build_client(
        context,
        *,
        facade=None,
        api_url=None,
        api_key=None,
        services=None,
    ):
        assert context is fake_app_context
        assert facade is None
        assert api_url == "https://api.example.com"
        assert api_key == "secret"
        return expected_client

    bootstrap._build_client_cached.clear()

    monkeypatch.setattr(
        bootstrap,
        "_build_facade_cached",
        fail_build_facade,
    )
    monkeypatch.setattr(
        bootstrap,
        "build_country_compare_client",
        build_client,
    )

    result = bootstrap._build_client_cached(
        fake_app_context,
        api_url,
        "secret",
    )

    assert result is expected_client

    bootstrap._build_client_cached.clear()
