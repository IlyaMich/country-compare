from __future__ import annotations

from fastapi.testclient import TestClient

from country_compare.api.dependencies import get_app_facade
from country_compare.api.main import create_app


class _PredictionServiceStub:
    def list_prediction_methods(self) -> list[dict[str, object]]:
        return [
            {
                "method_id": "linear_trend",
                "display_name": "Linear trend",
                "description": "Fits a simple linear trend.",
                "metadata": {},
            },
            {
                "method_id": "llm_forecast",
                "display_name": "LLM forecast — experimental",
                "description": "Uses the backend-configured LLM forecast service.",
                "metadata": {"experimental": True},
            },
        ]


class _FacadeStub:
    prediction = _PredictionServiceStub()


def test_prediction_methods_metadata_comes_from_backend_facade() -> None:
    app = create_app()
    app.dependency_overrides[get_app_facade] = lambda: _FacadeStub()

    try:
        client = TestClient(app)
        response = client.get("/api/v1/metadata/prediction-methods")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json() == {
        "methods": [
            {
                "method_id": "linear_trend",
                "display_name": "Linear trend",
                "description": "Fits a simple linear trend.",
                "metadata": {},
            },
            {
                "method_id": "llm_forecast",
                "display_name": "LLM forecast — experimental",
                "description": "Uses the backend-configured LLM forecast service.",
                "metadata": {"experimental": True},
            },
        ]
    }
