from __future__ import annotations

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from country_compare.api.dependencies import get_app_facade
from country_compare.api.main import create_app
from country_compare.api.settings import ApiSettings
from country_compare.services.errors import AppError
from country_compare.services.presentation_service import PresentationService
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
        self.weighted_score_error: AppError | None = None

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

        if self.weighted_score_error is not None:
            return _error_result(
                mode="weighted_score",
                request=request,
                error=self.weighted_score_error,
            )

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


class TopNValidationFacade:
    def __init__(self) -> None:
        self.presentation = PresentationService()

    def compare_single_metric(
        self,
        request: SingleMetricRequest,
    ) -> tuple[ComparisonResult, PresentationResult]:
        dataframe = pd.DataFrame(
            [
                {
                    "country_code": "AAA",
                    "country_name": "Alpha",
                    "metric_id": "oracle_metric",
                    "metric_name": "Oracle Metric",
                    "value": 10.0,
                    "normalized_value": 0.0,
                    "rank": 3,
                    "year": 2023,
                },
                {
                    "country_code": "BBB",
                    "country_name": "Beta",
                    "metric_id": "oracle_metric",
                    "metric_name": "Oracle Metric",
                    "value": 30.0,
                    "normalized_value": 1.0,
                    "rank": 1,
                    "year": 2023,
                },
                {
                    "country_code": "CCC",
                    "country_name": "Gamma",
                    "metric_id": "oracle_metric",
                    "metric_name": "Oracle Metric",
                    "value": 20.0,
                    "normalized_value": 0.5,
                    "rank": 2,
                    "year": 2023,
                },
            ]
        )

        result = ComparisonResult(
            mode="single_metric",
            request=request,
            dataframe=dataframe,
            metadata={
                "metric_id": "oracle_metric",
                "selected_countries": ["AAA", "BBB", "CCC"],
            },
        )

        return (
            result,
            self.presentation.build_single_metric_presentation(result),
        )

    def compare_multi_metric(
        self,
        request: MultiMetricRequest,
    ) -> tuple[ComparisonResult, PresentationResult]:
        dataframe = pd.DataFrame(
            [
                {
                    "country_code": "AAA",
                    "country_name": "Alpha",
                    "metric_id": "metric_alpha",
                    "metric_name": "Metric Alpha",
                    "value": 10.0,
                    "normalized_value": 0.0,
                    "rank": 3,
                    "year": 2023,
                },
                {
                    "country_code": "BBB",
                    "country_name": "Beta",
                    "metric_id": "metric_alpha",
                    "metric_name": "Metric Alpha",
                    "value": 30.0,
                    "normalized_value": 1.0,
                    "rank": 1,
                    "year": 2023,
                },
                {
                    "country_code": "CCC",
                    "country_name": "Gamma",
                    "metric_id": "metric_alpha",
                    "metric_name": "Metric Alpha",
                    "value": 20.0,
                    "normalized_value": 0.5,
                    "rank": 2,
                    "year": 2023,
                },
                {
                    "country_code": "AAA",
                    "country_name": "Alpha",
                    "metric_id": "metric_beta",
                    "metric_name": "Metric Beta",
                    "value": 30.0,
                    "normalized_value": 1.0,
                    "rank": 1,
                    "year": 2023,
                },
                {
                    "country_code": "BBB",
                    "country_name": "Beta",
                    "metric_id": "metric_beta",
                    "metric_name": "Metric Beta",
                    "value": 10.0,
                    "normalized_value": 0.0,
                    "rank": 3,
                    "year": 2023,
                },
                {
                    "country_code": "CCC",
                    "country_name": "Gamma",
                    "metric_id": "metric_beta",
                    "metric_name": "Metric Beta",
                    "value": 20.0,
                    "normalized_value": 0.5,
                    "rank": 2,
                    "year": 2023,
                },
            ]
        )

        result = ComparisonResult(
            mode="multi_metric",
            request=request,
            dataframe=dataframe,
            metadata={
                "metric_ids": ["metric_alpha", "metric_beta"],
                "selected_countries": ["AAA", "BBB", "CCC"],
            },
        )

        return (
            result,
            self.presentation.build_multi_metric_presentation(result),
        )

    def compare_weighted_score(
        self,
        request: WeightedScoreRequest,
    ) -> tuple[ComparisonResult, PresentationResult]:
        dataframe = pd.DataFrame(
            [
                {
                    "country_code": "AAA",
                    "country_name": "Alpha",
                    "weighted_score": 0.30,
                    "score_rank": 3,
                },
                {
                    "country_code": "BBB",
                    "country_name": "Beta",
                    "weighted_score": 0.80,
                    "score_rank": 1,
                },
                {
                    "country_code": "CCC",
                    "country_name": "Gamma",
                    "weighted_score": 0.50,
                    "score_rank": 2,
                },
            ]
        )

        result = ComparisonResult(
            mode="weighted_score",
            request=request,
            dataframe=dataframe,
            metadata={
                "profile_name": "oracle_profile",
                "selected_countries": ["AAA", "BBB", "CCC"],
            },
        )

        return (
            result,
            self.presentation.build_weighted_score_presentation(result),
        )


def _client_for(
    facade: FakeFacade,
    *,
    max_records: int = 500,
    max_countries: int = 50,
    max_metrics: int = 50,
    max_top_n: int = 100,
) -> TestClient:
    app = create_app(
        settings=ApiSettings(
            max_records=max_records,
            max_countries=max_countries,
            max_metrics=max_metrics,
            max_top_n=max_top_n,
        )
    )
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


@pytest.mark.parametrize(
    ("path", "payload"),
    [
        (
            "/api/v1/compare/single-metric",
            {
                "country_codes": ["ISR", "FRA"],
                "metric_id": "gdp_per_capita",
                "top_n": 2,
            },
        ),
        (
            "/api/v1/compare/multi-metric",
            {
                "country_codes": ["ISR", "FRA"],
                "metric_ids": ["gdp_per_capita", "life_expectancy"],
                "top_n": 2,
            },
        ),
        (
            "/api/v1/score/profile",
            {
                "country_codes": ["ISR", "FRA"],
                "profile_name": "economic_outlook",
                "top_n": 2,
            },
        ),
    ],
)
def test_comparison_top_n_limit_returns_400_before_service_call(
    path: str,
    payload: dict[str, object],
) -> None:
    facade = FakeFacade()
    client = _client_for(facade, max_top_n=1)

    response = client.post(path, json=payload)

    assert response.status_code == 400

    body = response.json()

    assert body["ok"] is False
    assert body["error"]["code"] == "input_limit_exceeded"
    assert body["error"]["details"]["field_errors"]["top_n"].startswith(
        "Requested 2 top rows"
    )

    assert facade.single_metric_requests == []
    assert facade.multi_metric_requests == []
    assert facade.weighted_score_requests == []


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
    assert response.json()["ok"] is False
    assert response.json()["error"]["code"] == "validation_failed"
    assert facade.single_metric_requests == []


def test_cmp_16_single_metric_top_n_preserves_global_rank_order() -> None:
    facade = TopNValidationFacade()
    client = _client_for(facade)

    response = client.post(
        "/api/v1/compare/single-metric",
        json={
            "country_codes": ["AAA", "BBB", "CCC"],
            "metric_id": "oracle_metric",
            "top_n": 2,
        },
    )

    assert response.status_code == 200

    table = response.json()["tables"]["main"]

    assert table["row_count"] == 2
    assert [row["country_code"] for row in table["records"]] == [
        "BBB",
        "CCC",
    ]
    assert [row["rank"] for row in table["records"]] == [1, 2]


def test_cmp_16_multi_metric_top_n_preserves_defined_long_table_order() -> None:
    facade = TopNValidationFacade()
    client = _client_for(facade)

    response = client.post(
        "/api/v1/compare/multi-metric",
        json={
            "country_codes": ["AAA", "BBB", "CCC"],
            "metric_ids": ["metric_alpha", "metric_beta"],
            "top_n": 2,
        },
    )

    assert response.status_code == 200

    table = response.json()["tables"]["main"]

    assert table["row_count"] == 2

    assert [
        (row["metric_id"], row["country_code"], row["rank"]) for row in table["records"]
    ] == [
        ("metric_alpha", "BBB", 1),
        ("metric_alpha", "CCC", 2),
    ]


def test_cmp_16_weighted_score_top_n_preserves_global_score_rank() -> None:
    facade = TopNValidationFacade()
    client = _client_for(facade)

    response = client.post(
        "/api/v1/score/profile",
        json={
            "country_codes": ["AAA", "BBB", "CCC"],
            "profile_name": "oracle_profile",
            "top_n": 2,
        },
    )

    assert response.status_code == 200

    table = response.json()["tables"]["main"]

    assert table["row_count"] == 2
    assert [row["country_code"] for row in table["records"]] == [
        "BBB",
        "CCC",
    ]
    assert [row["score_rank"] for row in table["records"]] == [1, 2]


def test_api_06_comparison_country_limit_returns_400_before_service_call() -> None:
    facade = FakeFacade()
    client = _client_for(facade, max_countries=1)

    response = client.post(
        "/api/v1/compare/single-metric",
        json={
            "country_codes": ["ISR", "FRA"],
            "metric_id": "gdp_per_capita",
        },
    )

    assert response.status_code == 400

    payload = response.json()

    assert payload["ok"] is False
    assert payload["error"]["code"] == "input_limit_exceeded"
    assert payload["error"]["details"]["field_errors"]["country_codes"].startswith(
        "Requested 2 countries"
    )

    assert facade.single_metric_requests == []


def test_api_06_comparison_metric_limit_returns_400_before_service_call() -> None:
    facade = FakeFacade()
    client = _client_for(facade, max_metrics=1)

    response = client.post(
        "/api/v1/compare/multi-metric",
        json={
            "country_codes": ["ISR", "FRA"],
            "metric_ids": [
                "gdp_per_capita",
                "life_expectancy",
            ],
        },
    )

    assert response.status_code == 400

    payload = response.json()

    assert payload["ok"] is False
    assert payload["error"]["code"] == "input_limit_exceeded"
    assert payload["error"]["details"]["field_errors"]["metric_ids"].startswith(
        "Requested 2 metrics"
    )

    assert facade.multi_metric_requests == []


def test_api_06_comparison_limits_accept_exact_boundary_values() -> None:
    facade = FakeFacade()

    client = _client_for(
        facade,
        max_countries=2,
        max_metrics=2,
        max_top_n=2,
    )

    response = client.post(
        "/api/v1/compare/multi-metric",
        json={
            "country_codes": ["ISR", "FRA"],
            "metric_ids": [
                "gdp_per_capita",
                "life_expectancy",
            ],
            "top_n": 2,
        },
    )

    assert response.status_code == 200
    assert response.json()["ok"] is True

    assert len(facade.multi_metric_requests) == 1

    service_request = facade.multi_metric_requests[0]

    assert len(service_request.countries) == 2
    assert len(service_request.metric_ids) == 2
    assert service_request.top_n == 2


def test_api_07_invalid_year_strategy_returns_validation_envelope() -> None:
    facade = FakeFacade()
    client = _client_for(facade)

    response = client.post(
        "/api/v1/compare/single-metric",
        json={
            "country_codes": ["ISR", "FRA"],
            "metric_id": "gdp_per_capita",
            "year_strategy": "not_a_real_strategy",
        },
    )

    assert response.status_code == 422

    payload = response.json()

    assert payload["ok"] is False
    assert payload["error"]["code"] == "validation_failed"
    assert payload["error"]["message"] == ("One or more request values are invalid.")

    assert facade.single_metric_requests == []


def test_api_07_missing_required_field_returns_validation_envelope() -> None:
    facade = FakeFacade()
    client = _client_for(facade)

    response = client.post(
        "/api/v1/compare/single-metric",
        json={
            "country_codes": ["ISR", "FRA"],
        },
    )

    assert response.status_code == 422

    payload = response.json()

    assert payload["ok"] is False
    assert payload["error"]["code"] == "validation_failed"

    field_errors = payload["error"]["details"]["field_errors"]

    assert any(field.endswith("metric_id") for field in field_errors)

    assert facade.single_metric_requests == []


def test_api_07_malformed_json_returns_sanitized_validation_envelope() -> None:
    facade = FakeFacade()
    client = _client_for(facade)

    raw_body = '{"country_codes": ["ISR", "FRA"],'

    response = client.post(
        "/api/v1/compare/single-metric",
        content=raw_body,
        headers={
            "Content-Type": "application/json",
        },
    )

    assert response.status_code == 422

    payload = response.json()

    assert payload["ok"] is False
    assert payload["error"]["code"] == "validation_failed"
    assert payload["error"]["message"] == ("One or more request values are invalid.")

    serialized = str(payload)

    assert "Traceback" not in serialized

    assert facade.single_metric_requests == []


def test_api_07_unknown_profile_returns_selection_error() -> None:
    facade = FakeFacade()

    facade.weighted_score_error = AppError(
        code="selection_invalid",
        title="Selection is invalid",
        user_message=("Please review the current selection and try again."),
        field_errors={"profile_name": ("Unknown scoring profile: missing_profile")},
    )

    client = _client_for(facade)

    response = client.post(
        "/api/v1/score/profile",
        json={
            "country_codes": ["ISR", "FRA"],
            "profile_name": "missing_profile",
        },
    )

    assert response.status_code == 400

    payload = response.json()

    assert payload["ok"] is False
    assert payload["error"]["code"] == "selection_invalid"

    assert "profile_name" in (payload["error"]["details"]["field_errors"])


def test_api_07_unknown_country_returns_selection_error() -> None:
    facade = FakeFacade()

    facade.single_metric_error = AppError(
        code="selection_invalid",
        title="Selection is invalid",
        user_message=("Please review the current selection and try again."),
        field_errors={
            "countries": (
                "The dataset does not contain these selected " "countries: ZZZ"
            )
        },
    )

    client = _client_for(facade)

    response = client.post(
        "/api/v1/compare/single-metric",
        json={
            "country_codes": ["ISR", "ZZZ"],
            "metric_id": "gdp_per_capita",
        },
    )

    assert response.status_code == 400

    payload = response.json()

    assert payload["ok"] is False
    assert payload["error"]["code"] == "selection_invalid"

    assert "countries" in (payload["error"]["details"]["field_errors"])
