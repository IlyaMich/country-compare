from __future__ import annotations

import json
from typing import Any

import httpx
import pandas as pd

from country_compare.clients.http import HttpCountryCompareClient


def _table_payload() -> dict[str, Any]:
    return {
        "row_count": 1,
        "column_count": 2,
        "columns": ["country_code", "score"],
        "records": [{"country_code": "ISR", "score": 1.0}],
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
