from __future__ import annotations

from fastapi.testclient import TestClient

from llm_forecast_service.main import create_app
from llm_forecast_service.schemas import (
    ForecastAdjustmentOutput,
    ForecastAdjustmentRequest,
    TimeSeriesPoint,
)
from llm_forecast_service.settings import ServiceSettings


class TooLargeAdjustmentProvider:
    def generate_adjustment(
        self, _request: ForecastAdjustmentRequest
    ) -> ForecastAdjustmentOutput:
        return ForecastAdjustmentOutput(
            forecast_points=[TimeSeriesPoint(year=2030, value=130.0)],
            rationale="too large",
        )


def _settings() -> ServiceSettings:
    return ServiceSettings(
        service_token="dev-token",
        mistral_api_key="dummy-key",
        mistral_model="mistral-large-latest",
        max_horizon_years=3,
        max_history_points=5,
    )


def _payload() -> dict[str, object]:
    return {
        "request_id": "req-1",
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


def test_forecast_adjust_requires_bearer_token() -> None:
    client = TestClient(create_app(settings=_settings()))

    response = client.post("/v1/forecast/adjust", json=_payload())

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "unauthorized"


def test_forecast_adjust_returns_baseline_echo_response() -> None:
    client = TestClient(create_app(settings=_settings()))

    response = client.post(
        "/v1/forecast/adjust",
        json=_payload(),
        headers={"Authorization": "Bearer dev-token"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["forecast_points"] == [{"year": 2030, "value": 100.0}]
    assert payload["metadata"]["provider"] == "mistral"
    assert payload["metadata"]["llm_calls"] == 0
    assert payload["warnings"]


def test_forecast_adjust_rejects_invalid_provider_output() -> None:
    client = TestClient(
        create_app(settings=_settings(), provider=TooLargeAdjustmentProvider())
    )

    response = client.post(
        "/v1/forecast/adjust",
        json=_payload(),
        headers={"Authorization": "Bearer dev-token"},
    )

    assert response.status_code == 502
    assert response.json()["error"]["code"] == "adjustment_exceeds_limit"
