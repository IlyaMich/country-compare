from __future__ import annotations

import httpx

from country_compare.clients.http import HttpCountryCompareClient


def test_http_client_exposes_service_shaped_ui_adapters() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/v1/metadata/countries":
            return httpx.Response(
                200,
                json={"countries": [{"code": "ISR", "name": "Israel"}]},
            )

        if request.url.path == "/api/v1/metadata/metrics":
            return httpx.Response(
                200,
                json={
                    "metrics": [
                        {
                            "metric_id": "gdp",
                            "display_name": "GDP",
                            "category": "economy",
                            "unit": "USD",
                        }
                    ]
                },
            )

        if request.url.path == "/api/v1/metadata/years":
            return httpx.Response(200, json={"years": [2020, 2021]})

        if request.url.path == "/api/v1/metadata/profiles":
            return httpx.Response(
                200,
                json={"profiles": [{"name": "default", "metric_count": 1}]},
            )

        return httpx.Response(404, json={"error": {"code": "not_found"}})

    http_client = httpx.Client(
        transport=httpx.MockTransport(handler),
        base_url="http://testserver",
    )
    client = HttpCountryCompareClient("http://testserver", http_client=http_client)

    services = client.as_ui_services()

    countries = services["dataset_service"].list_countries()
    metrics = services["dataset_service"].list_metrics()
    years = services["dataset_service"].list_years()
    profiles = services["config_service"].get_profile_summaries()

    assert countries[0].code == "ISR"
    assert metrics[0].metric_id == "gdp"
    assert years == (2020, 2021)
    assert profiles[0].name == "default"
