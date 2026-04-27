from __future__ import annotations

import pandas as pd
from fastapi.testclient import TestClient

from country_compare.api.dependencies import get_app_facade
from country_compare.api.main import create_app
from country_compare.api.settings import ApiSettings
from country_compare.services.errors import AppError
from country_compare.services.requests import (
    MultiMetricRequest,
    SingleMetricRequest,
    WeightedScoreRequest,
)
from country_compare.services.results import ComparisonResult, PresentationResult


class FakeFacade:
    def __init__(self) -> None:
        self.single_metric_requests: list[SingleMetricRequest] = []
        self.multi_metric_requests: list[MultiMetricRequest] = []
        self.weighted_score_requests: list[WeightedScoreRequest] = []
        self.single_metric_error: AppError | None = None

    def compare_single_metric(
        self,
        request: SingleMetricRequest,
    ) -> tuple[ComparisonResult, PresentationResult]:
        self.single_metric_requests.append(request)
        if self.single_metric_error is not None:
            return _error_result(
                mode="single_metric",
                request=request,
                error=self.single_metric_error,
            )
        return _success_result(
            mode="single_metric",
            request=request,
            table=pd.DataFrame(
                {
                    "country_code": ["ISR", "FRA"],
                    "country_name": ["Israel", "France"],
                    "metric_id": [request.metric_id, request.metric_id],
                    "year": [2024, 2024],
                    "value": [100.0, 90.0],
                    "rank": [1, 2],
                }
            ),
            summary={"status": "success", "title": "GDP per capita"},
            metadata={"metric_id": request.metric_id},
        )

    def compare_multi_metric(
        self,
        request: MultiMetricRequest,
    ) -> tuple[ComparisonResult, PresentationResult]:
        self.multi_metric_requests.append(request)
        table = pd.DataFrame(
            {
                "country_code": ["ISR", "ISR", "FRA", "FRA"],
                "metric_id": [
                    "gdp_per_capita",
                    "life_expectancy",
                    "gdp_per_capita",
                    "life_expectancy",
                ],
                "year": [2024, 2024, 2024, 2024],
                "value": [100.0, 82.0, 90.0, 83.0],
            }
        )
        wide_table = pd.DataFrame(
            {
                "country_code": ["ISR", "FRA"],
                "gdp_per_capita": [100.0, 90.0],
                "life_expectancy": [82.0, 83.0],
            }
        )
        return _success_result(
            mode="multi_metric",
            request=request,
            table=table,
            tables={"Wide comparison table": wide_table},
            summary={"status": "success", "title": "Multi-metric comparison"},
            metadata={"metric_ids": list(request.metric_ids)},
        )

    def compare_weighted_score(
        self,
        request: WeightedScoreRequest,
    ) -> tuple[ComparisonResult, PresentationResult]:
        self.weighted_score_requests.append(request)
        return _success_result(
            mode="weighted_score",
            request=request,
            table=pd.DataFrame(
                {
                    "country_code": ["ISR", "FRA"],
                    "weighted_score": [0.91, 0.85],
                    "score_rank": [1, 2],
                }
            ),
            summary={"status": "success", "title": "Weighted score"},
            metadata={"profile_name": request.profile_name},
        )


def test_single_metric_comparison_returns_result_envelope() -> None:
    facade = FakeFacade()
    client = _client_for(facade)

    response = client.post(
        "/api/v1/compare/single-metric",
        json={
            "country_codes": ["isr", "fra"],
            "metric_id": "gdp_per_capita",
            "year_strategy": "latest_per_metric",
            "top_n": 2,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["mode"] == "single_metric"
    assert payload["summary"] == {"status": "success", "title": "GDP per capita"}
    assert payload["metadata"] == {"metric_id": "gdp_per_capita"}
    assert payload["tables"]["main"]["columns"] == [
        "country_code",
        "country_name",
        "metric_id",
        "year",
        "value",
        "rank",
    ]
    assert payload["tables"]["main"]["records"][0] == {
        "country_code": "ISR",
        "country_name": "Israel",
        "metric_id": "gdp_per_capita",
        "year": 2024,
        "value": 100.0,
        "rank": 1,
    }
    assert payload["error"] is None

    assert len(facade.single_metric_requests) == 1
    service_request = facade.single_metric_requests[0]
    assert service_request.countries == ["ISR", "FRA"]
    assert service_request.metric_id == "gdp_per_capita"
    assert service_request.top_n == 2


def test_multi_metric_comparison_returns_main_and_extra_tables() -> None:
    facade = FakeFacade()
    client = _client_for(facade)

    response = client.post(
        "/api/v1/compare/multi-metric",
        json={
            "country_codes": ["ISR", "FRA"],
            "metric_ids": ["gdp_per_capita", "life_expectancy"],
            "year_strategy": "common_year",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["mode"] == "multi_metric"
    assert set(payload["tables"]) == {"main", "Wide comparison table"}
    assert payload["tables"]["main"]["row_count"] == 4
    assert payload["tables"]["Wide comparison table"]["row_count"] == 2

    assert len(facade.multi_metric_requests) == 1
    service_request = facade.multi_metric_requests[0]
    assert service_request.countries == ["ISR", "FRA"]
    assert service_request.metric_ids == ["gdp_per_capita", "life_expectancy"]
    assert service_request.year_strategy.value == "common_year"


def test_weighted_score_comparison_returns_result_envelope() -> None:
    facade = FakeFacade()
    client = _client_for(facade)

    response = client.post(
        "/api/v1/score/profile",
        json={
            "country_codes": ["ISR", "FRA"],
            "profile_name": "economic_outlook",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["mode"] == "weighted_score"
    assert payload["metadata"] == {"profile_name": "economic_outlook"}
    assert payload["tables"]["main"]["records"][0] == {
        "country_code": "ISR",
        "weighted_score": 0.91,
        "score_rank": 1,
    }

    assert len(facade.weighted_score_requests) == 1
    service_request = facade.weighted_score_requests[0]
    assert service_request.countries == ["ISR", "FRA"]
    assert service_request.profile_name == "economic_outlook"


def test_comparison_route_truncates_records_using_api_settings() -> None:
    facade = FakeFacade()
    client = _client_for(facade, max_records=1)

    response = client.post(
        "/api/v1/compare/single-metric",
        json={
            "country_codes": ["ISR", "FRA"],
            "metric_id": "gdp_per_capita",
        },
    )

    assert response.status_code == 200
    table = response.json()["tables"]["main"]
    assert table["row_count"] == 2
    assert table["records_truncated"] is True
    assert len(table["records"]) == 1


def test_comparison_service_error_returns_error_envelope() -> None:
    facade = FakeFacade()
    facade.single_metric_error = AppError(
        code="selection_invalid",
        title="Selection is invalid",
        user_message="Please review the current selection and try again.",
        technical_detail="{'metric_id': 'Unknown metric_id: bad_metric'}",
        field_errors={"metric_id": "Unknown metric_id: bad_metric"},
    )
    client = _client_for(facade)

    response = client.post(
        "/api/v1/compare/single-metric",
        json={
            "country_codes": ["ISR", "FRA"],
            "metric_id": "bad_metric",
        },
    )

    assert response.status_code == 400
    payload = response.json()
    assert payload["ok"] is False
    assert payload["mode"] == "single_metric"
    assert payload["tables"] == {}
    assert payload["error"] == {
        "code": "selection_invalid",
        "message": "Please review the current selection and try again.",
        "details": {
            "title": "Selection is invalid",
            "technical_detail": "{'metric_id': 'Unknown metric_id: bad_metric'}",
            "field_errors": {"metric_id": "Unknown metric_id: bad_metric"},
        },
    }


def test_target_year_strategy_without_target_year_returns_422() -> None:
    facade = FakeFacade()
    client = _client_for(facade)

    response = client.post(
        "/api/v1/compare/single-metric",
        json={
            "country_codes": ["ISR", "FRA"],
            "metric_id": "gdp_per_capita",
            "year_strategy": "target_year",
        },
    )

    assert response.status_code == 422
    assert facade.single_metric_requests == []


def _client_for(facade: FakeFacade, *, max_records: int = 500) -> TestClient:
    app = create_app(settings=ApiSettings(max_records=max_records))
    app.dependency_overrides[get_app_facade] = lambda: facade
    return TestClient(app)


def _success_result(
    *,
    mode: str,
    request: object,
    table: pd.DataFrame,
    summary: dict[str, object],
    metadata: dict[str, object],
    tables: dict[str, pd.DataFrame] | None = None,
) -> tuple[ComparisonResult, PresentationResult]:
    result = ComparisonResult(
        mode=mode,
        request=request,
        dataframe=table,
        metadata=metadata,
    )
    presentation = PresentationResult(
        mode=mode,
        request=request,
        summary=summary,
        table=table,
        tables=tables or {},
        metadata=metadata,
    )
    return result, presentation


def _error_result(
    *,
    mode: str,
    request: object,
    error: AppError,
) -> tuple[ComparisonResult, PresentationResult]:
    result = ComparisonResult(mode=mode, request=request, error=error)
    presentation = PresentationResult(mode=mode, request=request, error=error)
    return result, presentation
