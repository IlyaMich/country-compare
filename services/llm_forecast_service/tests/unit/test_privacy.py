from __future__ import annotations

from fastapi.testclient import TestClient

from llm_forecast_service.main import create_app
from llm_forecast_service.privacy import REDACTED, redact_mapping, safe_metadata
from llm_forecast_service.providers import BaselineEchoProvider
from llm_forecast_service.settings import ServiceSettings


def _settings(**overrides: object) -> ServiceSettings:
    values = {
        "service_token": "dev-token",
        "provider": "mistral",
        "mistral_api_key": "test-key",
        "mistral_model": "mistral-large-latest",
        "deployment_profile": "local",
        "require_zdr": False,
        "mistral_zdr_confirmed": False,
    }
    values.update(overrides)
    return ServiceSettings(**values)


def test_public_deployment_requires_zdr_confirmation() -> None:
    client = TestClient(
        create_app(
            settings=_settings(
                deployment_profile="public",
                require_zdr=True,
                mistral_zdr_confirmed=False,
            ),
            provider=BaselineEchoProvider(),
        )
    )

    response = client.get(
        "/ready",
        headers={"Authorization": "Bearer test-token"},
    )

    assert response.status_code == 503
    payload = response.json()
    assert payload["status"] == "not_ready"


def test_public_capabilities_fail_when_zdr_not_confirmed() -> None:
    client = TestClient(
        create_app(
            settings=_settings(
                deployment_profile="public",
                require_zdr=True,
                mistral_zdr_confirmed=False,
            ),
            provider=BaselineEchoProvider(),
        )
    )

    response = client.get(
        "/v1/capabilities",
        headers={"Authorization": "Bearer dev-token"},
    )

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "service_not_ready"


def test_public_deployment_ignores_debug_payload_logging() -> None:
    settings = _settings(
        deployment_profile="public",
        require_zdr=True,
        mistral_zdr_confirmed=True,
        debug_log_payloads=True,
    )

    assert settings.effective_debug_log_payloads is False


def test_redacts_sensitive_diagnostics() -> None:
    redacted = redact_mapping(
        {
            "provider": "mistral",
            "mistral_api_key": "secret",
            "nested": {
                "service_token": "token",
                "safe": "value",
            },
        }
    )

    assert redacted["mistral_api_key"] == REDACTED
    assert redacted["nested"]["service_token"] == REDACTED
    assert redacted["nested"]["safe"] == "value"


def test_safe_metadata_uses_allow_list() -> None:
    metadata = safe_metadata(
        {
            "provider": "mistral",
            "model": "mistral-large-latest",
            "prompt_version": "llm_forecast_mistral_v1",
            "mistral_api_key": "secret",
            "raw_provider_response": {"secret": "value"},
        }
    )

    assert metadata == {
        "provider": "mistral",
        "model": "mistral-large-latest",
        "prompt_version": "llm_forecast_mistral_v1",
    }


def test_safe_metadata_preserves_latency_and_queue_fields() -> None:
    metadata = safe_metadata(
        {
            "provider": "mistral",
            "model": "mistral-large-latest",
            "queue_wait_ms": 12,
            "provider_latency_ms": 34,
            "total_latency_ms": 46,
            "max_concurrent_requests": 1,
            "authorization": "Bearer secret",
            "raw_provider_response": "secret",
        }
    )

    assert metadata == {
        "provider": "mistral",
        "model": "mistral-large-latest",
        "queue_wait_ms": 12,
        "provider_latency_ms": 34,
        "total_latency_ms": 46,
        "max_concurrent_requests": 1,
    }
