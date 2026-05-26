from __future__ import annotations

import json

import httpx
import pytest

from llm_forecast_service.errors import ServiceError
from llm_forecast_service.providers import mistral as mistral_provider
from llm_forecast_service.providers.mistral import MistralProvider
from llm_forecast_service.schemas import (
    ForecastAdjustmentRequest,
    ForecastConstraints,
    TimeSeriesPoint,
)
from llm_forecast_service.settings import ServiceSettings


def _settings(**overrides: object) -> ServiceSettings:
    values = {
        "service_token": "dev-token",
        "mistral_api_key": "test-mistral-key",
        "mistral_model": "mistral-large-latest",
        "max_retries": 0,
    }
    values.update(overrides)
    return ServiceSettings(**values)


def _request() -> ForecastAdjustmentRequest:
    return ForecastAdjustmentRequest(
        request_id="req-1",
        country_code="ISR",
        country_name="Israel",
        metric_id="gdp_per_capita",
        metric_name="GDP per capita",
        unit="USD",
        history=[
            TimeSeriesPoint(year=2028, value=90.0),
            TimeSeriesPoint(year=2029, value=100.0),
        ],
        baseline_forecast=[TimeSeriesPoint(year=2030, value=100.0)],
        constraints=ForecastConstraints(
            max_adjustment_pct=15.0,
            horizon_years=1,
            allowed_years=[2030],
        ),
        prompt_version="llm_forecast_mistral_v1",
    )


def _mistral_response(content: object) -> dict[str, object]:
    return {
        "choices": [
            {
                "message": {
                    "content": json.dumps(content),
                }
            }
        ]
    }


@pytest.mark.asyncio
async def test_mistral_provider_parses_valid_response() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["Authorization"] == "Bearer test-mistral-key"

        body = json.loads(request.content)
        assert body["model"] == "mistral-large-latest"
        assert body["response_format"]["type"] == "json_schema"

        return httpx.Response(
            200,
            json=_mistral_response(
                {
                    "forecast_points": [{"year": 2030, "value": 105.0}],
                    "rationale": "Recent trend supports a small upward adjustment.",
                    "assumptions": ["Baseline remains broadly valid."],
                    "warnings": [],
                }
            ),
        )

    provider = MistralProvider(
        _settings(),
        transport=httpx.MockTransport(handler),
    )

    result = await provider.generate_adjustment(_request())

    assert result.forecast_points[0].year == 2030
    assert result.forecast_points[0].value == 105.0
    assert result.rationale


@pytest.mark.asyncio
async def test_mistral_provider_maps_invalid_json_to_provider_error() -> None:
    async def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "content": "not-json",
                        }
                    }
                ]
            },
        )

    provider = MistralProvider(
        _settings(),
        transport=httpx.MockTransport(handler),
    )

    with pytest.raises(ServiceError) as exc_info:
        await provider.generate_adjustment(_request())

    assert exc_info.value.code == "invalid_provider_response"
    assert exc_info.value.status_code == 502


@pytest.mark.asyncio
async def test_mistral_provider_maps_rate_limit() -> None:
    async def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, json={"error": {"message": "rate limited"}})

    provider = MistralProvider(
        _settings(),
        transport=httpx.MockTransport(handler),
    )

    with pytest.raises(ServiceError) as exc_info:
        await provider.generate_adjustment(_request())

    assert exc_info.value.code == "provider_rate_limited"
    assert exc_info.value.status_code == 429


@pytest.mark.asyncio
async def test_mistral_provider_maps_timeout() -> None:
    async def handler(_request: httpx.Request) -> httpx.Response:
        raise httpx.TimeoutException("timeout")

    provider = MistralProvider(
        _settings(),
        transport=httpx.MockTransport(handler),
    )

    with pytest.raises(ServiceError) as exc_info:
        await provider.generate_adjustment(_request())

    assert exc_info.value.code == "provider_timeout"
    assert exc_info.value.status_code == 504


@pytest.mark.asyncio
async def test_mistral_provider_retries_rate_limit_then_succeeds(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sleep_calls: list[tuple[int, str | None]] = []

    async def fake_retry_sleep(
        attempt_index: int,
        *,
        retry_after: str | None = None,
    ) -> None:
        sleep_calls.append((attempt_index, retry_after))

    monkeypatch.setattr(mistral_provider, "_retry_sleep", fake_retry_sleep)

    calls = 0

    async def handler(_request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1

        if calls == 1:
            return httpx.Response(
                429,
                headers={"Retry-After": "1"},
                json={"error": {"message": "rate limited"}},
            )

        return httpx.Response(
            200,
            json=_mistral_response(
                {
                    "forecast_points": [{"year": 2030, "value": 105.0}],
                    "rationale": "Retry succeeded.",
                    "assumptions": [],
                    "warnings": [],
                }
            ),
        )

    provider = MistralProvider(
        _settings(max_retries=1),
        transport=httpx.MockTransport(handler),
    )

    result = await provider.generate_adjustment(_request())

    assert result.forecast_points[0].value == 105.0
    assert calls == 2
    assert sleep_calls == [(0, "1")]


@pytest.mark.asyncio
async def test_mistral_provider_retries_server_error_then_succeeds(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sleep_calls: list[tuple[int, str | None]] = []

    async def fake_retry_sleep(
        attempt_index: int,
        *,
        retry_after: str | None = None,
    ) -> None:
        sleep_calls.append((attempt_index, retry_after))

    monkeypatch.setattr(mistral_provider, "_retry_sleep", fake_retry_sleep)

    calls = 0

    async def handler(_request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1

        if calls == 1:
            return httpx.Response(
                503,
                headers={"Retry-After": "2"},
                json={"error": {"message": "temporarily unavailable"}},
            )

        return httpx.Response(
            200,
            json=_mistral_response(
                {
                    "forecast_points": [{"year": 2030, "value": 104.0}],
                    "rationale": "Retry succeeded.",
                    "assumptions": [],
                    "warnings": [],
                }
            ),
        )

    provider = MistralProvider(
        _settings(max_retries=1),
        transport=httpx.MockTransport(handler),
    )

    result = await provider.generate_adjustment(_request())

    assert result.forecast_points[0].value == 104.0
    assert calls == 2
    assert sleep_calls == [(0, "2")]


@pytest.mark.asyncio
async def test_mistral_provider_retries_request_error_then_succeeds(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sleep_calls: list[tuple[int, str | None]] = []

    async def fake_retry_sleep(
        attempt_index: int,
        *,
        retry_after: str | None = None,
    ) -> None:
        sleep_calls.append((attempt_index, retry_after))

    monkeypatch.setattr(mistral_provider, "_retry_sleep", fake_retry_sleep)

    calls = 0

    async def handler(_request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1

        if calls == 1:
            raise httpx.ConnectError("temporary connection failure")

        return httpx.Response(
            200,
            json=_mistral_response(
                {
                    "forecast_points": [{"year": 2030, "value": 103.0}],
                    "rationale": "Retry succeeded.",
                    "assumptions": [],
                    "warnings": [],
                }
            ),
        )

    provider = MistralProvider(
        _settings(max_retries=1),
        transport=httpx.MockTransport(handler),
    )

    result = await provider.generate_adjustment(_request())

    assert result.forecast_points[0].value == 103.0
    assert calls == 2
    assert sleep_calls == [(0, None)]


def test_retry_after_delta_seconds_is_parsed_and_capped() -> None:
    assert mistral_provider._parse_retry_after_seconds("2") == 2.0
    assert mistral_provider._parse_retry_after_seconds("999") == 10.0
    assert mistral_provider._parse_retry_after_seconds("-1") == 0.0


def test_retry_after_invalid_value_is_safe() -> None:
    assert mistral_provider._parse_retry_after_seconds("not-a-date") == 0.0
    assert mistral_provider._parse_retry_after_seconds("") is None
    assert mistral_provider._parse_retry_after_seconds(None) is None
