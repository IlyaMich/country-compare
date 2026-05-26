from __future__ import annotations

from fastapi.testclient import TestClient

from llm_forecast_service.main import create_app
from llm_forecast_service.settings import ServiceSettings


def _ready_settings(**overrides: object) -> ServiceSettings:
    values = {
        "service_token": "dev-token",
        "mistral_api_key": "dummy-key",
        "mistral_model": "mistral-large-latest",
    }
    values.update(overrides)
    return ServiceSettings(**values)


def test_health_returns_ok_without_provider_config() -> None:
    client = TestClient(create_app(settings=ServiceSettings()))

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "service": "llm-forecast-service"}


def test_ready_returns_503_when_provider_config_missing() -> None:
    client = TestClient(create_app(settings=ServiceSettings()))

    response = client.get("/ready")

    assert response.status_code == 503
    payload = response.json()
    assert payload["status"] == "not_ready"
    assert "LLM_SERVICE_TOKEN is not configured" in payload["issues"]
    assert "MISTRAL_API_KEY is not configured" in payload["issues"]


def test_ready_returns_200_when_configured() -> None:
    client = TestClient(create_app(settings=_ready_settings()))

    response = client.get("/ready")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ready"
    assert payload["provider"] == "mistral"
    assert payload["model"] == "mistral-large-latest"
    assert payload["issues"] == []


def test_ready_enforces_public_zdr_gate() -> None:
    client = TestClient(
        create_app(
            settings=_ready_settings(
                deployment_profile="public",
                require_zdr=False,
                mistral_zdr_confirmed=False,
            )
        )
    )

    response = client.get("/ready")

    assert response.status_code == 503
    assert (
        "LLM_REQUIRE_ZDR must be true for public deployments"
        in response.json()["issues"]
    )


def test_capabilities_requires_bearer_token() -> None:
    client = TestClient(create_app(settings=_ready_settings()))

    response = client.get("/v1/capabilities")

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "unauthorized"


def test_capabilities_rejects_invalid_bearer_token() -> None:
    client = TestClient(create_app(settings=_ready_settings()))

    response = client.get("/v1/capabilities", headers={"Authorization": "Bearer wrong"})

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "unauthorized"


def test_capabilities_returns_configured_limits() -> None:
    client = TestClient(create_app(settings=_ready_settings(max_horizon_years=7)))

    response = client.get(
        "/v1/capabilities",
        headers={"Authorization": "Bearer dev-token"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["provider"] == "mistral"
    assert payload["supports_bounded_adjustment"] is True
    assert payload["max_horizon_years"] == 7
