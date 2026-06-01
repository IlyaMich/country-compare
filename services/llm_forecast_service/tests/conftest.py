from __future__ import annotations

from collections.abc import Callable
from typing import Any

import pytest

from llm_forecast_service.settings import ServiceSettings


@pytest.fixture
def auth_headers() -> dict[str, str]:
    return {"Authorization": "Bearer dev-token"}


@pytest.fixture
def service_settings_factory() -> Callable[..., ServiceSettings]:
    def factory(**overrides: Any) -> ServiceSettings:
        values: dict[str, Any] = {
            "service_token": "dev-token",
            "provider": "mistral",
            "mistral_api_key": "test-mistral-key",
            "mistral_model": "mistral-large-latest",
            "deployment_profile": "local",
            "require_zdr": False,
            "mistral_zdr_confirmed": False,
            "max_concurrent_requests": 1,
            "queue_timeout_seconds": 1.0,
        }
        values.update(overrides)
        return ServiceSettings(**values)

    return factory


@pytest.fixture
def forecast_adjust_payload_factory() -> Callable[..., dict[str, Any]]:
    def factory(
        *,
        request_id: str = "req-1",
        history: list[dict[str, float | int]] | None = None,
        baseline_forecast: list[dict[str, float | int]] | None = None,
        horizon_years: int = 1,
        allowed_years: list[int] | None = None,
        max_adjustment_pct: float = 15.0,
    ) -> dict[str, Any]:
        if history is None:
            history = [
                {"year": 2028, "value": 90.0},
                {"year": 2029, "value": 100.0},
            ]
        if baseline_forecast is None:
            baseline_forecast = [{"year": 2030, "value": 100.0}]
        if allowed_years is None:
            allowed_years = [int(point["year"]) for point in baseline_forecast]

        return {
            "request_id": request_id,
            "country_code": "ISR",
            "country_name": "Israel",
            "metric_id": "gdp_per_capita",
            "metric_name": "GDP per capita",
            "unit": "USD",
            "history": history,
            "baseline_forecast": baseline_forecast,
            "constraints": {
                "max_adjustment_pct": max_adjustment_pct,
                "horizon_years": horizon_years,
                "allowed_years": allowed_years,
            },
            "prompt_version": "llm_forecast_mistral_v1",
        }

    return factory