from __future__ import annotations

import json

import httpx
import pytest

from country_compare.prediction.llm.client import LLMForecastRequest
from country_compare.prediction.llm.remote_client import (
    RemoteLLMForecastClient,
    RemoteLLMForecastError,
)


def test_remote_client_sends_auth_and_converts_response() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1/forecast/adjust"
        assert request.headers["authorization"] == "Bearer test-token"

        payload = json.loads(request.content)
        assert payload["country_code"] == "ISR"
        assert payload["constraints"]["allowed_years"] == [2024]

        return httpx.Response(
            200,
            json={
                "forecast_points": [{"year": 2024, "value": 42.0}],
                "rationale": "Remote rationale.",
                "assumptions": ["Remote assumption."],
                "warnings": ["Remote warning."],
                "metadata": {
                    "provider": "mistral",
                    "model": "mistral-large-latest",
                    "prompt_version": "llm_forecast_v1",
                },
            },
        )

    http_client = httpx.Client(transport=httpx.MockTransport(handler))
    client = RemoteLLMForecastClient(
        service_url="http://llm-forecast:8080",
        service_token="test-token",
        timeout_seconds=5,
        max_adjustment_pct=20.0,
        http_client=http_client,
    )

    response = client.forecast(
        LLMForecastRequest(
            country_code="ISR",
            country_name="Israel",
            metric_id="gdp_per_capita",
            metric_name="GDP per capita",
            unit="USD",
            history=[{"year": 2023, "value": 40.0}],
            baseline_forecast=[{"year": 2024, "value": 40.0}],
            horizon_years=1,
            prompt_version="llm_forecast_v1",
        )
    )

    assert response.forecast_points[0].year == 2024
    assert response.forecast_points[0].value == pytest.approx(42.0)
    assert response.rationale == "Remote rationale."
    assert response.assumptions == ["Remote assumption."]
    assert response.warnings == ["Remote warning."]
    assert response.raw_provider_metadata["provider"] == "mistral"


def test_remote_client_capabilities_available() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1/capabilities"
        assert request.headers["authorization"] == "Bearer test-token"

        return httpx.Response(
            200,
            json={
                "provider": "mistral",
                "model": "mistral-large-latest",
                "supports_structured_output": True,
                "supports_bounded_adjustment": True,
                "max_series_per_request": 1,
                "max_horizon_years": 10,
                "max_history_points": 40,
                "one_call_per_series": True,
                "zdr_required": False,
                "zdr_confirmed": False,
            },
        )

    http_client = httpx.Client(transport=httpx.MockTransport(handler))
    client = RemoteLLMForecastClient(
        service_url="http://llm-forecast:8080",
        service_token="test-token",
        timeout_seconds=5,
        max_adjustment_pct=20.0,
        http_client=http_client,
    )

    assert client.is_available() is True


def test_remote_client_maps_http_error_without_token_leak() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            503,
            json={
                "error": {
                    "code": "service_not_ready",
                    "message": "LLM forecast service is not ready.",
                    "details": {},
                }
            },
        )

    http_client = httpx.Client(transport=httpx.MockTransport(handler))
    client = RemoteLLMForecastClient(
        service_url="http://llm-forecast:8080",
        service_token="secret-token",
        timeout_seconds=5,
        max_adjustment_pct=20.0,
        http_client=http_client,
    )

    with pytest.raises(RemoteLLMForecastError) as exc_info:
        client.capabilities()

    assert "service_not_ready" in str(exc_info.value)
    assert "secret-token" not in str(exc_info.value)
