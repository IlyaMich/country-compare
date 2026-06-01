from __future__ import annotations

import asyncio
from typing import Any

import httpx

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


class SlowProvider:
    provider_name = "baseline_echo"
    model_name = "baseline_echo"

    async def generate_adjustment(self, _request: Any) -> ForecastAdjustmentOutput:
        await asyncio.sleep(0.08)
        return ForecastAdjustmentOutput(
            forecast_points=[{"year": 2030, "value": 100.0}],
            rationale="ok",
            assumptions=[],
            warnings=[],
        )


def test_queue_acquire_timeout_returns_429() -> None:
    app = create_app(
        settings=_settings(
            provider="baseline_echo",
            mistral_api_key="",
            max_concurrent_requests=1,
            queue_timeout_seconds=0.01,
        ),
        provider=SlowProvider(),
    )
    transport = httpx.ASGITransport(app=app)

    async def run_requests() -> list[httpx.Response]:
        async with httpx.AsyncClient(
            transport=transport, base_url="http://testserver"
        ) as client:
            return await asyncio.gather(
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

    responses = asyncio.run(run_requests())

    assert sorted(response.status_code for response in responses) == [200, 429]
    rejected = next(response for response in responses if response.status_code == 429)
    assert rejected.json()["error"]["code"] == "service_overloaded"
