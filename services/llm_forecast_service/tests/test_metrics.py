from __future__ import annotations

from fastapi.testclient import TestClient

from llm_forecast_service import metrics
from llm_forecast_service.main import create_app
from llm_forecast_service.schemas import ForecastAdjustmentOutput
from llm_forecast_service.settings import ServiceSettings


class _UnsafeAdjustmentProvider:
    @property
    def provider_name(self) -> str:
        return "test_provider"

    @property
    def model_name(self) -> str:
        return "test_model"

    async def generate_adjustment(self, request) -> ForecastAdjustmentOutput:
        return ForecastAdjustmentOutput(
            forecast_points=[
                {
                    "year": request.baseline_forecast[0].year,
                    "value": request.baseline_forecast[0].value * 10,
                }
            ],
            rationale="Returns a structurally valid but unsafe adjustment.",
            assumptions=[],
            warnings=[],
        )


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


def test_request_validation_error_records_metric() -> None:
    metrics.reset_metrics_for_tests()
    app = create_app(settings=_settings(protect_metrics=False))
    client = TestClient(app)

    response = client.post(
        "/v1/forecast/adjust",
        headers={"Authorization": "Bearer test-token"},
        json={"invalid": "payload"},
    )

    assert response.status_code == 422

    metrics_response = client.get("/metrics")

    assert metrics_response.status_code == 200
    assert "llm_validation_failures_total" in metrics_response.text
    assert 'code="invalid_request"' in metrics_response.text


def test_provider_output_validation_error_records_metric() -> None:
    metrics.reset_metrics_for_tests()
    app = create_app(
        settings=_settings(protect_metrics=False),
        provider=_UnsafeAdjustmentProvider(),
    )
    client = TestClient(app)

    response = client.post(
        "/v1/forecast/adjust",
        headers={"Authorization": "Bearer test-token"},
        json={
            "request_id": "req-1",
            "country_code": "ISR",
            "metric_id": "gdp_per_capita",
            "prompt_version": "test",
            "history": [{"year": 2021, "value": 100.0}],
            "baseline_forecast": [{"year": 2022, "value": 100.0}],
            "constraints": {
                "horizon_years": 1,
                "max_adjustment_pct": 10.0,
            },
        },
    )

    assert response.status_code in {400, 413, 422, 502}

    payload = response.json()
    error_code = payload["error"]["code"]

    metrics_response = client.get("/metrics")

    assert metrics_response.status_code == 200
    assert "llm_validation_failures_total" in metrics_response.text
    assert f'code="{error_code}"' in metrics_response.text
