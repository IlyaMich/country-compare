from __future__ import annotations

from typing import Any

from fastapi.testclient import TestClient

from llm_forecast_service.main import create_app
from llm_forecast_service.providers import BaselineEchoProvider
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


def test_explicit_baseline_provider_reports_effective_metadata() -> None:
    client = TestClient(
        create_app(
            settings=_settings(provider="baseline_echo", mistral_api_key=""),
            provider=BaselineEchoProvider(),
        )
    )

    response = client.post(
        "/v1/forecast/adjust",
        json=_payload(),
        headers={"Authorization": "Bearer dev-token"},
    )

    assert response.status_code == 200
    metadata = response.json()["metadata"]
    assert metadata["provider"] == "baseline_echo"
    assert metadata["model"] == "baseline_echo"
    assert metadata["queue_wait_ms"] >= 0
    assert metadata["max_concurrent_requests"] == 1
