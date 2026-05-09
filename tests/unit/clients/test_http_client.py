from __future__ import annotations

import json
from types import SimpleNamespace
from typing import Any, cast

import httpx
import pandas as pd

from country_compare.clients.http import HttpCountryCompareClient
from country_compare.services.results import PresentationResult


def _table_payload() -> dict[str, Any]:
    return {
        "row_count": 1,
        "column_count": 2,
        "columns": ["country_code", "score"],
        "records": [{"country_code": "ISR", "score": 1.0}],
        "records_truncated": False,
    }


def _ranked_table_payload() -> dict[str, Any]:
    return {
        "row_count": 2,
        "column_count": 6,
        "columns": [
            "rank",
            "country_code",
            "country_name",
            "metric_name",
            "value",
            "normalized_value",
        ],
        "records": [
            {
                "rank": 1,
                "country_code": "ISR",
                "country_name": "Israel",
                "metric_name": "GDP",
                "value": 10.0,
                "normalized_value": 1.0,
            },
            {
                "rank": 2,
                "country_code": "FRA",
                "country_name": "France",
                "metric_name": "GDP",
                "value": 8.0,
                "normalized_value": 0.5,
            },
        ],
        "records_truncated": False,
    }


def test_http_client_maps_country_metadata() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/v1/metadata/countries"
        return httpx.Response(
            200,
            json={"countries": [{"code": "ISR", "name": "Israel"}]},
        )

    http_client = httpx.Client(
        transport=httpx.MockTransport(handler),
        base_url="http://testserver",
    )
    client = HttpCountryCompareClient("http://testserver", http_client=http_client)

    countries = client.list_countries()

    assert countries[0].code == "ISR"
    assert countries[0].name == "Israel"


def test_http_client_maps_comparison_envelope_to_presentation() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/v1/compare/single-metric"
        body = json.loads(request.content.decode("utf-8"))
        assert body["country_codes"] == ["ISR", "FRA"]
        assert body["metric_id"] == "gdp"

        return httpx.Response(
            200,
            json={
                "ok": True,
                "mode": "single_metric",
                "request": body,
                "summary": {"title": "GDP comparison"},
                "metadata": {"source": "test"},
                "diagnostics": {},
                "warnings": [],
                "tables": {"main": _table_payload()},
                "error": None,
            },
        )

    http_client = httpx.Client(
        transport=httpx.MockTransport(handler),
        base_url="http://testserver",
    )
    client = HttpCountryCompareClient("http://testserver", http_client=http_client)

    presentation = client.run_single_metric_comparison(
        country_codes=["ISR", "FRA"],
        metric_id="gdp",
        year_strategy="latest_per_metric",
    )

    assert presentation.mode == "single_metric"
    assert presentation.summary["title"] == "GDP comparison"
    assert isinstance(presentation.table, pd.DataFrame)
    assert presentation.table.iloc[0]["country_code"] == "ISR"


def test_http_client_maps_backend_error_to_result_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "ok": False,
                "mode": "single_metric",
                "summary": {},
                "metadata": {},
                "diagnostics": {},
                "warnings": [],
                "tables": {},
                "error": {
                    "code": "invalid_metric",
                    "title": "Invalid metric",
                    "user_message": "Unknown metric.",
                },
            },
        )

    http_client = httpx.Client(
        transport=httpx.MockTransport(handler),
        base_url="http://testserver",
    )
    client = HttpCountryCompareClient("http://testserver", http_client=http_client)

    presentation = client.run_single_metric_comparison(
        country_codes=["ISR", "FRA"],
        metric_id="bad",
        year_strategy="latest_per_metric",
    )

    assert presentation.error is not None
    assert presentation.error.code == "invalid_metric"


def test_http_client_calls_predicted_multi_metric_endpoint() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/v1/prediction/compare/multi-metric"
        body = json.loads(request.content.decode("utf-8"))
        assert body["metric_ids"] == ["gdp_per_capita", "life_expectancy"]
        assert body["country_codes"] == ["ISR", "FRA"]
        assert body["horizon_years"] == 3

        return httpx.Response(
            200,
            json={
                "ok": True,
                "mode": "predicted_multi_metric_comparison",
                "request": body,
                "summary": {},
                "metadata": {"client_mode": "http"},
                "diagnostics": {},
                "warnings": [],
                "tables": {"main": _table_payload()},
                "error": None,
            },
        )

    http_client = httpx.Client(
        transport=httpx.MockTransport(handler),
        base_url="http://testserver",
    )
    client = HttpCountryCompareClient("http://testserver", http_client=http_client)

    result = client.run_predicted_multi_metric_comparison(
        metric_ids=["gdp_per_capita", "life_expectancy"],
        country_codes=["ISR", "FRA"],
        horizon_years=3,
        forecast_year=2027,
        method="linear_trend",
        comparison_options={"top_n": 2},
    )

    assert result.ok
    assert result.mode == "predicted_multi_metric_comparison"
    assert result.error is None
    assert isinstance(result.dataframe, pd.DataFrame)
    assert result.predicted_comparison_result is not None
    assert (
        result.predicted_comparison_result.comparison_df.iloc[0]["country_code"]
        == "ISR"
    )
    assert result.request == {
        "country_codes": ["ISR", "FRA"],
        "metric_ids": ["gdp_per_capita", "life_expectancy"],
        "horizon_years": 3,
        "forecast_year": 2027,
        "method": "linear_trend",
        "fallback_method": "last_observed",
        "comparison_options": {"top_n": 2},
    }


def test_http_client_sends_api_key_header() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["x-api-key"] == "secret"
        return httpx.Response(
            200,
            json={"countries": [{"code": "ISR", "name": "Israel"}]},
        )

    http_client = httpx.Client(
        transport=httpx.MockTransport(handler),
        base_url="http://testserver",
    )
    client = HttpCountryCompareClient(
        "http://testserver", http_client=http_client, api_key="secret"
    )

    assert client.list_countries()[0].code == "ISR"


def test_http_presentation_adapter_rebuilds_chart_from_remote_table() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content.decode("utf-8"))
        return httpx.Response(
            200,
            json={
                "ok": True,
                "mode": "single_metric",
                "request": body,
                "summary": {"title": "Remote GDP comparison"},
                "metadata": {"source": "mock-backend"},
                "diagnostics": {},
                "warnings": [],
                "tables": {"main": _ranked_table_payload()},
                "charts": {},
                "error": None,
            },
        )

    http_client = httpx.Client(
        transport=httpx.MockTransport(handler),
        base_url="http://testserver",
    )
    client = HttpCountryCompareClient("http://testserver", http_client=http_client)
    services = client.as_ui_services()

    request = SimpleNamespace(
        countries=["ISR", "FRA"],
        metric_id="gdp",
        year_strategy="latest_per_metric",
        target_year=None,
        top_n=None,
    )
    result = services["comparison_service"].run_single_metric(cast(Any, request))
    presentation = services["presentation_service"].build_single_metric_presentation(
        result
    )

    assert presentation.summary == {"title": "Remote GDP comparison"}
    assert presentation.chart is not None
    assert isinstance(presentation.table, pd.DataFrame)


def test_http_presentation_service_adapter_supports_export_controls() -> None:
    service = cast(
        Any,
        HttpCountryCompareClient("http://backend.test").as_ui_services()[
            "presentation_service"
        ],
    )
    table = pd.DataFrame([{"country_code": "DEU", "value": 1.5}])

    csv_bytes = service.export_table_csv_bytes(table)
    assert csv_bytes.startswith(b"country_code,value")

    metadata_bytes = service.export_metadata_json_bytes({"source": "http"})
    assert json.loads(metadata_bytes.decode("utf-8")) == {"source": "http"}

    bundle_bytes = service.export_presentation_bundle_json_bytes(
        PresentationResult(mode="single_metric", request={}, table=table)
    )
    bundle = json.loads(bundle_bytes.decode("utf-8"))
    assert bundle["mode"] == "single_metric"
