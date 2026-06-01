from __future__ import annotations

import asyncio
import logging
from typing import Any

import httpx
import pytest
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
        "baseline_forecast": [
            {"year": 2030, "value": 100.0},
        ],
        "constraints": {
            "max_adjustment_pct": 15.0,
            "horizon_years": 1,
            "allowed_years": [2030],
        },
        "prompt_version": "llm_forecast_mistral_v1",
    }


class SlowProvider:
    provider_name = "mistral"

    def __init__(self) -> None:
        self.active = 0
        self.max_active = 0

    async def generate_adjustment(self, _request: Any) -> ForecastAdjustmentOutput:
        self.active += 1
        self.max_active = max(self.max_active, self.active)
        try:
            await asyncio.sleep(0.05)
            return ForecastAdjustmentOutput(
                forecast_points=[{"year": 2030, "value": 101.0}],
                rationale="Small adjustment.",
                assumptions=[],
                warnings=[],
            )
        finally:
            self.active -= 1


@pytest.mark.asyncio
async def test_forecast_adjust_respects_concurrency_limit() -> None:
    provider = SlowProvider()
    app = create_app(
        settings=_settings(max_concurrent_requests=1),
        provider=provider,
    )

    transport = httpx.ASGITransport(app=app)

    async with httpx.AsyncClient(
        transport=transport,
        base_url="http://testserver",
    ) as client:
        responses = await asyncio.gather(
            client.post(
                "/v1/forecast/adjust",
                json=_payload("req-1"),
                headers={"Authorization": "Bearer dev-token"},
            ),
            client.post(
                "/v1/forecast/adjust",
                json=_payload("req-2"),
                headers={"Authorization": "Bearer dev-token"},
            ),
        )

    assert [response.status_code for response in responses] == [200, 200]
    assert provider.max_active == 1


def test_forecast_adjust_logs_safe_operational_metadata(
    caplog: pytest.LogCaptureFixture,
) -> None:
    provider = SlowProvider()
    app = create_app(settings=_settings(), provider=provider)

    caplog.set_level(logging.INFO, logger="llm_forecast_service.main")

    with TestClient(app) as client:
        response = client.post(
            "/v1/forecast/adjust",
            json=_payload(),
            headers={"Authorization": "Bearer dev-token"},
        )

    assert response.status_code == 200

    log_text = caplog.text
    assert "llm_forecast_adjust_completed" in log_text
    assert "request_id=req-1" in log_text
    assert "country_code=ISR" in log_text
    assert "metric_id=gdp_per_capita" in log_text
    assert "status=ok" in log_text

    assert "test-mistral-key" not in log_text
    assert "dev-token" not in log_text
    assert "baseline_forecast" not in log_text
    assert "history" not in log_text
    assert "90.0" not in log_text
    assert "100.0" not in log_text


def test_invalid_concurrency_setting_fails_readiness() -> None:
    settings = _settings(max_concurrent_requests=0)

    assert "LLM_MAX_CONCURRENT_REQUESTS must be at least 1" in (
        settings.readiness_issues()
    )
