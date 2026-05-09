from __future__ import annotations

from fastapi.testclient import TestClient

from country_compare.api.dependencies import get_app_facade
from country_compare.api.main import create_app
from country_compare.api.settings import ApiSettings
from country_compare.services.models import CountryOption


class FakeDatasetService:
    def list_countries(self) -> tuple[CountryOption, ...]:
        return (CountryOption(code="ISR", name="Israel"),)


class FakeFacade:
    def __init__(self) -> None:
        self.dataset = FakeDatasetService()


def test_api_key_auth_keeps_health_public_but_protects_api_routes() -> None:
    app = create_app(settings=ApiSettings(api_key="secret"))
    app.dependency_overrides[get_app_facade] = lambda: FakeFacade()

    with TestClient(app) as client:
        health_response = client.get("/health")
        unauthenticated_response = client.get("/api/v1/metadata/countries")
        authenticated_response = client.get(
            "/api/v1/metadata/countries", headers={"X-API-Key": "secret"}
        )

    assert health_response.status_code == 200
    assert unauthenticated_response.status_code == 401
    assert unauthenticated_response.json()["error"]["code"] == "authentication_required"
    assert authenticated_response.status_code == 200
    assert authenticated_response.json() == {
        "countries": [{"code": "ISR", "name": "Israel"}]
    }
