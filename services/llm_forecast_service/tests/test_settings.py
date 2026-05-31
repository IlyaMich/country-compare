from __future__ import annotations

from typing import Any

import pytest

from llm_forecast_service.main import create_app
from llm_forecast_service.settings import ServiceSettings, SettingsError


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


def test_settings_invalid_bool_env_var_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLM_DEBUG_LOG_PAYLOADS", "maybe")

    with pytest.raises(SettingsError, match="LLM_DEBUG_LOG_PAYLOADS"):
        ServiceSettings.from_env()


def test_settings_non_positive_limit_env_var_raises(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("LLM_MAX_CONCURRENT_REQUESTS", "0")

    with pytest.raises(SettingsError, match="LLM_MAX_CONCURRENT_REQUESTS"):
        ServiceSettings.from_env()


def test_baseline_provider_must_be_explicit() -> None:
    app = create_app(settings=_settings(mistral_api_key=""))

    assert app.state.provider.provider_name == "mistral"
    assert "MISTRAL_API_KEY is not configured" in app.state.settings.readiness_issues()
