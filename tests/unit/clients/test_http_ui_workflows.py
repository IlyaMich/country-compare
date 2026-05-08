from __future__ import annotations

import json
from typing import Any

import httpx
import pandas as pd

from country_compare.clients.http import HttpCountryCompareClient
from country_compare.services.requests import SingleMetricRequest


def _table_payload() -> dict[str, Any]:
    return {
        "row_count": 2,
        "column_count": 3,
        "columns": ["country_code", "country_name", "value"],
        "records": [
            {"country_code": "ISR", "country_name": "Israel", "value": 1.0},
            {"country_code": "FRA", "country_name": "France", "value": 2.0},
        ],
        "records_truncated": False,
    }


def _envelope(*, mode: str, request_body: dict[str, Any]) -> dict[str, Any]:
    return {
        "ok": True,
        "mode": mode,
        "request": request_body,
        "summary": {"title": f"{mode} result"},
        "metadata": {"source": "mock-backend"},
        "diagnostics": {},
        "warnings": [],
        "tables": {"main": _table_payload()},
        "charts": {},
        "error": None,
    }


def test_http_ui_services_run_single_metric_comparison_workflow() -> None:
    seen_bodies: list[dict[str, Any]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "POST"
        assert request.url.path == "/api/v1/compare/single-metric"

        body = json.loads(request.content.decode("utf-8"))
        seen_bodies.append(body)

        assert body == {
            "country_codes": ["ISR", "FRA"],
            "metric_id": "gdp_per_capita",
            "year_strategy": "latest_per_metric",
            "top_n": 2,
        }

        return httpx.Response(
            200,
            json=_envelope(mode="single_metric", request_body=body),
        )

    http_client = httpx.Client(
        transport=httpx.MockTransport(handler),
        base_url="http://testserver",
    )
    client = HttpCountryCompareClient("http://testserver", http_client=http_client)
    services = client.as_ui_services()

    comparison_service = services["comparison_service"]
    presentation_service = services["presentation_service"]

    request = SingleMetricRequest(
        countries=[" isr ", "fra", "ISR"],
        metric_id=" gdp_per_capita ",
        year_strategy="latest_per_metric",
        top_n=2,
    )

    result = comparison_service.run_single_metric(request)
    presentation = presentation_service.build_single_metric_presentation(result)

    assert result.ok
    assert presentation.ok
    assert presentation.mode == "single_metric"
    assert presentation.summary["title"] == "single_metric result"
    assert isinstance(presentation.table, pd.DataFrame)
    assert presentation.table.iloc[0]["country_code"] == "ISR"
    assert seen_bodies == [
        {
            "country_codes": ["ISR", "FRA"],
            "metric_id": "gdp_per_capita",
            "year_strategy": "latest_per_metric",
            "top_n": 2,
        }
    ]


def test_http_ui_services_run_predicted_profile_workflow() -> None:
    seen_bodies: list[dict[str, Any]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "POST"
        assert request.url.path == "/api/v1/prediction/compare/profile"

        body = json.loads(request.content.decode("utf-8"))
        seen_bodies.append(body)

        assert body == {
            "country_codes": ["ISR", "FRA"],
            "profile_name": "economic_outlook",
            "horizon_years": 3,
            "forecast_year": 2027,
            "method": "linear_trend",
            "fallback_method": "last_observed",
            "comparison_options": {"top_n": 2},
        }

        return httpx.Response(
            200,
            json=_envelope(
                mode="predicted_profile_comparison",
                request_body=body,
            ),
        )

    http_client = httpx.Client(
        transport=httpx.MockTransport(handler),
        base_url="http://testserver",
    )
    client = HttpCountryCompareClient("http://testserver", http_client=http_client)
    services = client.as_ui_services()

    prediction_service = services["prediction_service"]

    result = prediction_service.run_predicted_profile_comparison(
        profile_name="economic_outlook",
        country_codes=["ISR", "FRA"],
        horizon_years=3,
        forecast_year=2027,
        method="linear_trend",
        comparison_options={"top_n": 2},
    )

    assert result.ok
    assert result.mode == "predicted_profile_comparison"
    assert isinstance(result.dataframe, pd.DataFrame)
    assert result.dataframe.iloc[1]["country_code"] == "FRA"
    assert seen_bodies == [
        {
            "country_codes": ["ISR", "FRA"],
            "profile_name": "economic_outlook",
            "horizon_years": 3,
            "forecast_year": 2027,
            "method": "linear_trend",
            "fallback_method": "last_observed",
            "comparison_options": {"top_n": 2},
        }
    ]
