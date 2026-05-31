from __future__ import annotations

import io
import logging

import pytest
from fastapi.testclient import TestClient

from country_compare.api.main import create_app
from country_compare.api.metrics import metrics_registry
from country_compare.api.request_context import configure_api_logging
from country_compare.api.security import api_key_required
from country_compare.api.settings import ApiSettings


@pytest.fixture(autouse=True)
def reset_metrics() -> None:
    metrics_registry.reset()


def test_development_without_api_key_allows_protected_route() -> None:
    app = create_app(
        ApiSettings(
            runtime_env="development",
            api_key=None,
            auth_required=False,
            enable_docs=True,
        )
    )

    response = TestClient(app).get("/ready")

    assert response.status_code != 401


def test_production_without_api_key_fails_startup(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("COUNTRY_COMPARE_API_ENV", "production")
    monkeypatch.delenv("COUNTRY_COMPARE_API_KEY", raising=False)

    with pytest.raises(ValueError, match="COUNTRY_COMPARE_API_KEY"):
        ApiSettings.from_env()


def test_valid_key_accepted_and_missing_or_invalid_key_rejected() -> None:
    settings = ApiSettings(
        runtime_env="production", api_key="secret", auth_required=True
    )
    app = create_app(settings)
    client = TestClient(app)

    assert client.get("/ready").status_code == 401
    assert client.get("/ready", headers={"X-API-Key": "wrong"}).status_code == 401
    assert client.get("/ready", headers={"X-API-Key": "secret"}).status_code != 401
    assert (
        client.get("/ready", headers={"Authorization": "Bearer secret"}).status_code
        != 401
    )


def test_api_key_not_logged_for_auth_failures(caplog: pytest.LogCaptureFixture) -> None:
    settings = ApiSettings(
        runtime_env="production", api_key="secret-token", auth_required=True
    )
    app = create_app(settings)

    with caplog.at_level(logging.WARNING, logger="country_compare.api.security"):
        TestClient(app).get("/ready", headers={"X-API-Key": "secret-token-but-wrong"})

    assert "secret-token" not in caplog.text
    assert "secret-token-but-wrong" not in caplog.text
    assert "api.auth_failure" in caplog.text


def test_metrics_disabled_by_default() -> None:
    app = create_app(ApiSettings(runtime_env="development", api_key=None))

    response = TestClient(app).get("/metrics")

    assert response.status_code == 404


def test_metrics_enabled_and_counter_increments() -> None:
    app = create_app(
        ApiSettings(
            runtime_env="development", enable_metrics=True, protect_metrics=False
        )
    )
    client = TestClient(app)

    client.get("/health")
    response = client.get("/metrics")

    assert response.status_code == 200
    assert "country_compare_api_requests_total" in response.text
    assert 'path="/health"' in response.text


def test_metrics_endpoint_can_be_protected() -> None:
    app = create_app(
        ApiSettings(
            runtime_env="production",
            api_key="secret",
            auth_required=True,
            enable_metrics=True,
            protect_metrics=True,
        )
    )
    client = TestClient(app)

    assert client.get("/metrics").status_code == 401
    assert client.get("/metrics", headers={"X-API-Key": "secret"}).status_code == 200


def test_docs_can_be_protected() -> None:
    app = create_app(
        ApiSettings(
            runtime_env="production",
            api_key="secret",
            auth_required=True,
            enable_docs=True,
            protect_docs=True,
        )
    )
    client = TestClient(app)

    assert client.get("/openapi.json").status_code == 401
    assert (
        client.get("/openapi.json", headers={"X-API-Key": "secret"}).status_code == 200
    )


def test_configurable_path_rules() -> None:
    settings = ApiSettings(
        protected_prefixes=("/private",),
        public_paths=("/ready",),
    )

    assert not api_key_required("/ready", api_settings=settings)
    assert api_key_required("/private/report", api_settings=settings)
    assert not api_key_required("/api/v1/metadata", api_settings=settings)


def test_invalid_log_level_fails() -> None:
    with pytest.raises(ValueError, match="COUNTRY_COMPARE_API_LOG_LEVEL"):
        ApiSettings(log_level="verbose")


def test_too_large_numeric_limit_fails() -> None:
    with pytest.raises(ValueError, match="COUNTRY_COMPARE_API_MAX_RECORDS"):
        ApiSettings(max_records=10_001)


def test_configure_logging_preserves_existing_handlers() -> None:
    logger = logging.getLogger("country_compare.api.access")
    previous_handlers = list(logger.handlers)
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    logger.handlers = [handler]
    try:
        configure_api_logging(
            level="INFO", log_format="json", propagate=True, clear_handlers=False
        )
        assert handler in logger.handlers
        assert logger.propagate is True
    finally:
        logger.handlers = previous_handlers
