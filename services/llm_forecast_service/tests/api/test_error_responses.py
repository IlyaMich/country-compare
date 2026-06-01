from __future__ import annotations

from typing import Any

from fastapi.testclient import TestClient

from llm_forecast_service.main import create_app
from llm_forecast_service.schemas import ForecastAdjustmentOutput
from llm_forecast_service.settings import ServiceSettings


def _settings(**overrides: Any) -> ServiceSettings:
    values: dict[str, Any] = {
        "service_token": "dev-token",
        "provider": "mistral",
        "mistral_api_key": "test-mistral-key",
        "mistral_model": "mistral-large-latest",
        "max_concurrent_requests": 1,
        "queue_timeout_seconds": 1.0,
    }
    values.update(overrides)
    return ServiceSettings(**values)


def _payload(request_id: str = "req-1") -> dict[str, Any]:
    return {
        "request_id": request_id,
        "country_code": "ISR",
        "country_name": "Israel",
        "metric_id": "gdp_per_capita",
        "metric_name": "GDP per capita",
        "unit": "USD",
        "history": [
            {"year": 2028, "value": 90.0},
            {"year": 2029, "value": 100.0},
        ],
        "baseline_forecast": [{"year": 2030, "value": 100.0}],
        "constraints": {
            "max_adjustment_pct": 15.0,
            "horizon_years": 1,
            "allowed_years": [2030],
        },
        "prompt_version": "llm_forecast_mistral_v1",
    }


class ExplodingProvider:
    provider_name = "baseline_echo"
    model_name = "baseline_echo"

    async def generate_adjustment(self, _request: Any) -> ForecastAdjustmentOutput:
        raise RuntimeError("secret raw provider failure")


def test_request_validation_error_sanitizes_input_and_includes_request_id() -> None:
    client = TestClient(create_app(settings=_settings()))

    response = client.post(
        "/v1/forecast/adjust",
        json={"request_id": "req-1", "history": "secret raw input"},
        headers={"Authorization": "Bearer dev-token", "X-Request-ID": "rid-123"},
    )

    assert response.status_code == 422
    body = response.json()
    assert body["error"]["details"]["request_id"] == "rid-123"
    assert "input" not in str(body)
    assert "secret raw input" not in str(body)
    assert response.headers["X-Request-ID"] == "rid-123"


def test_unexpected_exception_returns_sanitized_500() -> None:
    client = TestClient(
        create_app(
            settings=_settings(provider="baseline_echo", mistral_api_key=""),
            provider=ExplodingProvider(),
        ),
        raise_server_exceptions=False,
    )

    response = client.post(
        "/v1/forecast/adjust",
        json=_payload(),
        headers={"Authorization": "Bearer dev-token", "X-Request-ID": "rid-500"},
    )

    assert response.status_code == 500
    body = response.json()
    assert body["error"]["code"] == "internal_error"
    assert body["error"]["details"]["request_id"] == "rid-500"
    assert "secret raw provider failure" not in str(body)
