from __future__ import annotations

from typing import Any

import pandas as pd
from fastapi.testclient import TestClient

from country_compare.api.dependencies import get_app_facade
from country_compare.api.main import create_app
from country_compare.api.settings import ApiSettings
from country_compare.services.errors import AppError
from country_compare.services.results import PredictionServiceResult


class FakeFacade:
    def __init__(self) -> None:
        self.single_metric_requests: list[dict[str, Any]] = []
        self.backtest_requests: list[dict[str, Any]] = []
        self.predicted_single_metric_requests: list[dict[str, Any]] = []
        self.predicted_profile_requests: list[dict[str, Any]] = []
        self.single_metric_error: AppError | None = None

    def predict_single_metric_for_countries(
        self, **kwargs: Any
    ) -> PredictionServiceResult:
        self.single_metric_requests.append(dict(kwargs))
        if self.single_metric_error is not None:
            return _error_result(
                mode="single_metric_countries_prediction",
                request=kwargs,
                error=self.single_metric_error,
            )
        forecast = pd.DataFrame(
            {
                "country_code": ["ISR", "FRA"],
                "metric_id": [kwargs["metric_id"], kwargs["metric_id"]],
                "year": [2025, 2025],
                "forecast_value": [101.0, 91.0],
                "forecast_horizon": [1, 1],
                "prediction_method": ["linear_trend", "linear_trend"],
            }
        )
        combined = pd.DataFrame(
            {
                "country_code": ["ISR", "ISR"],
                "metric_id": [kwargs["metric_id"], kwargs["metric_id"]],
                "year": [2024, 2025],
                "value": [100.0, 101.0],
                "series_kind": ["actual", "forecast"],
            }
        )
        comparison_ready = forecast.rename(columns={"forecast_value": "value"})
        return PredictionServiceResult(
            mode="single_metric_countries_prediction",
            request=kwargs,
            prediction_result={
                "forecast_df": forecast,
                "combined_df": combined,
                "comparison_ready_df": comparison_ready,
            },
            dataframe=forecast,
            summary={"result_type": "prediction", "forecast_years": [2025]},
            metadata={"scenario_id": kwargs["scenario_id"]},
            diagnostics={"warnings": ["sparse history"]},
            warnings=["sparse history"],
        )

    def backtest_prediction(self, **kwargs: Any) -> PredictionServiceResult:
        self.backtest_requests.append(dict(kwargs))
        actual_vs_predicted = pd.DataFrame(
            {
                "country_code": [kwargs["country_code"]],
                "metric_id": [kwargs["metric_id"]],
                "year": [2023],
                "actual_value": [100.0],
                "predicted_value": [98.5],
            }
        )
        return PredictionServiceResult(
            mode="prediction_backtest",
            request=kwargs,
            backtest_result={"actual_vs_predicted_df": actual_vs_predicted},
            dataframe=actual_vs_predicted,
            summary={"result_type": "backtest", "metrics": {"mae": 1.5}},
            metadata={"holdout_years": kwargs["holdout_years"]},
            diagnostics={"status_counts": {"ok": 1}},
        )

    def compare_predicted_single_metric(self, **kwargs: Any) -> PredictionServiceResult:
        self.predicted_single_metric_requests.append(dict(kwargs))
        comparison = pd.DataFrame(
            {
                "country_code": ["ISR", "FRA"],
                "metric_id": [kwargs["metric_id"], kwargs["metric_id"]],
                "year": [2027, 2027],
                "value": [103.0, 93.0],
                "rank": [1, 2],
            }
        )
        forecast = comparison.drop(columns=["rank"])
        return PredictionServiceResult(
            mode="predicted_single_metric_comparison",
            request=kwargs,
            prediction_result={"forecast_df": forecast},
            predicted_comparison_result={"comparison_df": comparison},
            dataframe=comparison,
            summary={
                "result_type": "predicted_comparison",
                "selected_forecast_year": kwargs["forecast_year"],
            },
            metadata={"metric_id": kwargs["metric_id"]},
        )

    def compare_predicted_profile(self, **kwargs: Any) -> PredictionServiceResult:
        self.predicted_profile_requests.append(dict(kwargs))
        comparison = pd.DataFrame(
            {
                "country_code": ["ISR", "FRA"],
                "profile_name": [kwargs["profile_name"], kwargs["profile_name"]],
                "score": [0.92, 0.88],
                "rank": [1, 2],
            }
        )
        return PredictionServiceResult(
            mode="predicted_profile_comparison",
            request=kwargs,
            predicted_comparison_result={"comparison_df": comparison},
            dataframe=comparison,
            summary={
                "result_type": "predicted_comparison",
                "selected_forecast_horizon": kwargs["forecast_horizon"],
            },
            metadata={"profile_name": kwargs["profile_name"]},
        )


def test_single_metric_prediction_returns_result_envelope() -> None:
    facade = FakeFacade()
    client = _client_for(facade)

    response = client.post(
        "/api/v1/prediction/single-metric",
        json={
            "country_codes": ["isr", "fra"],
            "metric_id": "gdp_per_capita",
            "horizon_years": 2,
            "method": "linear_trend",
            "fallback_method": "last_observed",
            "scenario_id": "baseline",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["mode"] == "single_metric_countries_prediction"
    assert payload["summary"] == {
        "result_type": "prediction",
        "forecast_years": [2025],
    }
    assert payload["metadata"] == {"scenario_id": "baseline"}
    assert payload["diagnostics"] == {"warnings": ["sparse history"]}
    assert payload["warnings"] == ["sparse history"]
    assert set(payload["tables"]) == {
        "main",
        "forecast",
        "actual_and_forecast",
        "comparison_ready",
    }
    assert payload["tables"]["forecast"]["records"][0] == {
        "country_code": "ISR",
        "metric_id": "gdp_per_capita",
        "year": 2025,
        "forecast_value": 101.0,
        "forecast_horizon": 1,
        "prediction_method": "linear_trend",
    }
    assert payload["error"] is None

    assert len(facade.single_metric_requests) == 1
    service_request = facade.single_metric_requests[0]
    assert service_request["country_codes"] == ["ISR", "FRA"]
    assert service_request["metric_id"] == "gdp_per_capita"
    assert service_request["horizon_years"] == 2
    assert service_request["method"].value == "linear_trend"
    assert service_request["fallback_method"].value == "last_observed"
    assert service_request["include_actuals"] is True
    assert service_request["fail_fast"] is False
    assert service_request["scenario_id"] == "baseline"


def test_backtest_returns_result_envelope_for_one_country() -> None:
    facade = FakeFacade()
    client = _client_for(facade)

    response = client.post(
        "/api/v1/prediction/backtest",
        json={
            "country_codes": ["ISR"],
            "metric_id": "gdp_per_capita",
            "holdout_years": 2,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["mode"] == "prediction_backtest"
    assert set(payload["tables"]) == {"main", "actual_vs_predicted"}
    assert payload["tables"]["actual_vs_predicted"]["records"][0] == {
        "country_code": "ISR",
        "metric_id": "gdp_per_capita",
        "year": 2023,
        "actual_value": 100.0,
        "predicted_value": 98.5,
    }

    assert len(facade.backtest_requests) == 1
    service_request = facade.backtest_requests[0]
    assert service_request["country_code"] == "ISR"
    assert service_request["metric_id"] == "gdp_per_capita"
    assert service_request["holdout_years"] == 2


def test_predicted_single_metric_comparison_returns_result_envelope() -> None:
    facade = FakeFacade()
    client = _client_for(facade)

    response = client.post(
        "/api/v1/prediction/compare/single-metric",
        json={
            "country_codes": ["ISR", "FRA"],
            "metric_id": "gdp_per_capita",
            "horizon_years": 3,
            "forecast_year": 2027,
            "comparison_options": {"top_n": 2},
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["mode"] == "predicted_single_metric_comparison"
    assert payload["summary"] == {
        "result_type": "predicted_comparison",
        "selected_forecast_year": 2027,
    }
    assert set(payload["tables"]) == {
        "main",
        "forecast",
        "predicted_comparison",
    }
    assert payload["tables"]["predicted_comparison"]["records"][0] == {
        "country_code": "ISR",
        "metric_id": "gdp_per_capita",
        "year": 2027,
        "value": 103.0,
        "rank": 1,
    }

    assert len(facade.predicted_single_metric_requests) == 1
    service_request = facade.predicted_single_metric_requests[0]
    assert service_request["country_codes"] == ["ISR", "FRA"]
    assert service_request["metric_id"] == "gdp_per_capita"
    assert service_request["horizon_years"] == 3
    assert service_request["forecast_year"] == 2027
    assert service_request["forecast_horizon"] is None
    assert service_request["comparison_options"] == {"top_n": 2}


def test_predicted_profile_comparison_returns_result_envelope() -> None:
    facade = FakeFacade()
    client = _client_for(facade)

    response = client.post(
        "/api/v1/prediction/compare/profile",
        json={
            "country_codes": ["ISR", "FRA"],
            "profile_name": "economic_outlook",
            "horizon_years": 3,
            "forecast_horizon": 2,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["mode"] == "predicted_profile_comparison"
    assert payload["metadata"] == {"profile_name": "economic_outlook"}
    assert set(payload["tables"]) == {"main", "predicted_comparison"}
    assert payload["tables"]["predicted_comparison"]["records"][0] == {
        "country_code": "ISR",
        "profile_name": "economic_outlook",
        "score": 0.92,
        "rank": 1,
    }

    assert len(facade.predicted_profile_requests) == 1
    service_request = facade.predicted_profile_requests[0]
    assert service_request["country_codes"] == ["ISR", "FRA"]
    assert service_request["profile_name"] == "economic_outlook"
    assert service_request["forecast_horizon"] == 2
    assert service_request["forecast_year"] is None


def test_prediction_route_truncates_records_using_api_settings() -> None:
    facade = FakeFacade()
    client = _client_for(facade, max_records=1)

    response = client.post(
        "/api/v1/prediction/single-metric",
        json={
            "country_codes": ["ISR", "FRA"],
            "metric_id": "gdp_per_capita",
            "horizon_years": 2,
        },
    )

    assert response.status_code == 200
    table = response.json()["tables"]["forecast"]
    assert table["row_count"] == 2
    assert table["records_truncated"] is True
    assert len(table["records"]) == 1


def test_prediction_service_error_returns_error_envelope() -> None:
    facade = FakeFacade()
    facade.single_metric_error = AppError(
        code="unsupported_method",
        title="Unsupported prediction method",
        user_message="Prediction method is not supported.",
        technical_detail="method='bad_method'",
        field_errors={"method": "bad_method"},
    )
    client = _client_for(facade)

    response = client.post(
        "/api/v1/prediction/single-metric",
        json={
            "country_codes": ["ISR"],
            "metric_id": "gdp_per_capita",
            "horizon_years": 2,
        },
    )

    assert response.status_code == 400
    payload = response.json()
    assert payload["ok"] is False
    assert payload["mode"] == "single_metric_countries_prediction"
    assert payload["tables"] == {}
    assert payload["error"] == {
        "code": "unsupported_method",
        "message": "Prediction method is not supported.",
        "details": {
            "title": "Unsupported prediction method",
            "technical_detail": "method='bad_method'",
            "field_errors": {"method": "bad_method"},
        },
    }


def test_backtest_with_multiple_countries_returns_422() -> None:
    facade = FakeFacade()
    client = _client_for(facade)

    response = client.post(
        "/api/v1/prediction/backtest",
        json={
            "country_codes": ["ISR", "FRA"],
            "metric_id": "gdp_per_capita",
            "holdout_years": 2,
        },
    )

    assert response.status_code == 422
    assert facade.backtest_requests == []


def test_predicted_comparison_with_year_and_horizon_returns_422() -> None:
    facade = FakeFacade()
    client = _client_for(facade)

    response = client.post(
        "/api/v1/prediction/compare/single-metric",
        json={
            "country_codes": ["ISR", "FRA"],
            "metric_id": "gdp_per_capita",
            "horizon_years": 3,
            "forecast_year": 2027,
            "forecast_horizon": 2,
        },
    )

    assert response.status_code == 422
    assert facade.predicted_single_metric_requests == []


def _client_for(facade: FakeFacade, *, max_records: int = 500) -> TestClient:
    app = create_app(settings=ApiSettings(max_records=max_records))
    app.dependency_overrides[get_app_facade] = lambda: facade
    return TestClient(app)


def _error_result(
    *,
    mode: str,
    request: object,
    error: AppError,
) -> PredictionServiceResult:
    return PredictionServiceResult(mode=mode, request=request, error=error)
