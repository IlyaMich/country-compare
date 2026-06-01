from __future__ import annotations

from fastapi.testclient import TestClient

from llm_forecast_service.main import create_app
from llm_forecast_service.settings import ServiceSettings


def test_request_id_echoed_on_health() -> None:
    client = TestClient(create_app(settings=ServiceSettings()))

    response = client.get("/health", headers={"X-Request-ID": "rid-health"})

    assert response.status_code == 200
    assert response.headers["X-Request-ID"] == "rid-health"
