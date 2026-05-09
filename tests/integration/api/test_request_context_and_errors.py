from __future__ import annotations

from fastapi.testclient import TestClient

from country_compare.api.main import create_app


def test_request_id_header_is_echoed_on_success() -> None:
    app = create_app()
    with TestClient(app) as client:
        response = client.get("/health", headers={"X-Request-ID": "req-test"})
    assert response.status_code == 200
    assert response.headers["X-Request-ID"] == "req-test"


def test_request_id_header_is_generated_when_missing() -> None:
    app = create_app()
    with TestClient(app) as client:
        response = client.get("/health")
    assert response.status_code == 200
    assert response.headers["X-Request-ID"]


def test_unexpected_errors_are_sanitized_and_logged(capsys) -> None:
    app = create_app()

    @app.get("/boom")
    def boom() -> None:
        raise RuntimeError("secret internal failure")

    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.get("/boom", headers={"X-Request-ID": "req-boom"})
    assert response.status_code == 500
    assert response.headers["X-Request-ID"] == "req-boom"
    payload = response.json()
    assert payload["error"]["code"] == "unexpected_error"
    assert "technical_detail" not in payload["error"]["details"]
    assert "secret internal failure" not in str(payload)

    captured = capsys.readouterr()
    assert "api.unhandled_exception" in captured.err
    assert "secret internal failure" in captured.err
