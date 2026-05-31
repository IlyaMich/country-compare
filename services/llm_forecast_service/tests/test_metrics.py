from __future__ import annotations

from fastapi.testclient import TestClient

from llm_forecast_service import metrics
from llm_forecast_service.main import create_app
from llm_forecast_service.settings import ServiceSettings


def _settings(*, protect_metrics: bool = False) -> ServiceSettings:
    return ServiceSettings(
        service_token="test-token",
        provider="baseline_echo",
        deployment_profile="local",
        enable_metrics=True,
        protect_metrics=protect_metrics,
    )


def test_metrics_endpoint_exposes_http_metrics() -> None:
    metrics.reset_metrics_for_tests()
    app = create_app(settings=_settings(protect_metrics=False))
    client = TestClient(app)

    client.get("/health")
    response = client.get("/metrics")

    assert response.status_code == 200
    assert "llm_http_requests_total" in response.text
    assert 'path="/health"' in response.text


def test_metrics_endpoint_can_be_protected() -> None:
    metrics.reset_metrics_for_tests()
    app = create_app(settings=_settings(protect_metrics=True))
    client = TestClient(app)

    response = client.get("/metrics")

    assert response.status_code == 401

    authorized = client.get(
        "/metrics",
        headers={"Authorization": "Bearer test-token"},
    )

    assert authorized.status_code == 200


def test_auth_failure_records_metric() -> None:
    metrics.reset_metrics_for_tests()
    app = create_app(settings=_settings(protect_metrics=False))
    client = TestClient(app)

    client.get("/v1/capabilities")
    response = client.get("/metrics")

    assert response.status_code == 200
    assert "llm_auth_failures_total" in response.text
    assert 'reason="missing_bearer_token"' in response.text


def test_queue_rejection_metric_can_be_recorded() -> None:
    metrics.reset_metrics_for_tests()

    metrics.record_queue_rejection()
    rendered = metrics.render_metrics()

    assert "llm_queue_rejections_total" in rendered
