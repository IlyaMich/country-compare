from __future__ import annotations

from collections.abc import Iterator

import pytest

from country_compare.api import llm_readiness
from country_compare.api.llm_readiness import (
    build_llm_ready_response,
    reset_llm_readiness_state_for_tests,
)
from country_compare.prediction.llm.forecasters import LLMForecastSettings
from country_compare.prediction.llm.remote_client import RemoteLLMForecastError


@pytest.fixture(autouse=True)
def _reset_state(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    reset_llm_readiness_state_for_tests()
    monkeypatch.setenv("COUNTRY_COMPARE_LLM_READY_CACHE_TTL_SECONDS", "10")
    monkeypatch.setenv("COUNTRY_COMPARE_LLM_READY_FAILURE_COOLDOWN_SECONDS", "30")
    monkeypatch.setenv("COUNTRY_COMPARE_LLM_READY_FAILURE_THRESHOLD", "2")
    yield
    reset_llm_readiness_state_for_tests()


def _settings() -> LLMForecastSettings:
    return LLMForecastSettings(
        enabled=True,
        service_url="http://llm-service:8001",
        service_token="token",
        service_timeout_seconds=1.0,
    )


class _CapabilitiesClient:
    calls = 0

    def __init__(self, **_: object) -> None:
        pass

    def capabilities(self) -> dict[str, object]:
        type(self).calls += 1
        return {
            "supports_structured_output": True,
            "supports_bounded_adjustment": True,
            "max_series_per_request": 1,
            "max_horizon_years": 5,
        }


class _FailingClient:
    calls = 0

    def __init__(self, **_: object) -> None:
        pass

    def capabilities(self) -> dict[str, object]:
        type(self).calls += 1
        raise RemoteLLMForecastError("upstream token rejected at secret-host")


def test_llm_ready_response_caches_success(monkeypatch: pytest.MonkeyPatch) -> None:
    _CapabilitiesClient.calls = 0
    monkeypatch.setattr(llm_readiness, "load_llm_forecast_settings", _settings)
    monkeypatch.setattr(llm_readiness, "RemoteLLMForecastClient", _CapabilitiesClient)

    first = build_llm_ready_response()
    second = build_llm_ready_response()

    assert first.status == "ready"
    assert second.status == "ready"
    assert _CapabilitiesClient.calls == 1


def test_llm_ready_response_sanitizes_remote_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _FailingClient.calls = 0
    monkeypatch.setattr(llm_readiness, "load_llm_forecast_settings", _settings)
    monkeypatch.setattr(llm_readiness, "RemoteLLMForecastClient", _FailingClient)

    payload = build_llm_ready_response()

    assert payload.status == "not_ready"
    assert payload.error == "LLM readiness check failed."
    assert "secret-host" not in payload.model_dump_json()
    assert "token rejected" not in payload.model_dump_json()


def test_llm_ready_response_enters_cooldown_after_repeated_failures(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    now = 1000.0
    _FailingClient.calls = 0
    monkeypatch.setattr(llm_readiness, "load_llm_forecast_settings", _settings)
    monkeypatch.setattr(llm_readiness, "RemoteLLMForecastClient", _FailingClient)
    monkeypatch.setenv("COUNTRY_COMPARE_LLM_READY_CACHE_TTL_SECONDS", "0")
    monkeypatch.setattr(llm_readiness.time, "monotonic", lambda: now)

    first = build_llm_ready_response()
    second = build_llm_ready_response()
    third = build_llm_ready_response()

    assert first.error == "LLM readiness check failed."
    assert second.error == "LLM readiness check failed."
    assert third.error == "LLM readiness check is temporarily unavailable; retry later."
    assert _FailingClient.calls == 2


def test_llm_ready_config_warnings_are_user_safe(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        llm_readiness,
        "load_llm_forecast_settings",
        lambda: LLMForecastSettings(enabled=False, service_url="", service_token=""),
    )

    payload = build_llm_ready_response()

    assert payload.status == "not_ready"
    assert "COUNTRY_COMPARE" not in payload.model_dump_json()
