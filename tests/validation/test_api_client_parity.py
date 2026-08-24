from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

import pandas as pd
from fastapi.testclient import TestClient

from country_compare.api.dependencies import get_app_facade
from country_compare.api.main import create_app
from country_compare.api.settings import ApiSettings
from country_compare.clients.http import HttpCountryCompareClient
from country_compare.clients.local import LocalCountryCompareClient
from country_compare.services.presentation_service import PresentationService
from country_compare.services.results import (
    AppMessage,
    ComparisonResult,
    PresentationResult,
)


class _ParityComparisonService:
    def run_single_metric(self, request: Any) -> ComparisonResult:
        dataframe = pd.DataFrame(
            [
                {
                    "rank": 1,
                    "country_code": "ISR",
                    "country_name": "Israel",
                    "metric_id": "gdp_per_capita",
                    "value": 30.0,
                    "normalized_value": 1.0,
                },
                {
                    "rank": 2,
                    "country_code": "FRA",
                    "country_name": "France",
                    "metric_id": "gdp_per_capita",
                    "value": 20.0,
                    "normalized_value": 0.5,
                },
            ]
        )

        return ComparisonResult(
            mode="single_metric",
            request=request,
            dataframe=dataframe,
            metadata={
                "dataset_version": "api-09-fixture-v1",
                "source": "synthetic",
            },
            diagnostics={
                "oracle_case": "API-09",
                "coverage": {
                    "ISR": 1.0,
                    "FRA": 1.0,
                },
            },
            warnings=[
                "Synthetic parity warning.",
            ],
        )


class _ParityPresentationService(PresentationService):
    def build_single_metric_presentation(
        self,
        result: ComparisonResult,
    ) -> PresentationResult:
        assert result.dataframe is not None

        table = result.dataframe.copy(deep=True)

        audit_table = pd.DataFrame(
            [
                {
                    "country_code": "ISR",
                    "included": True,
                },
                {
                    "country_code": "FRA",
                    "included": True,
                },
            ]
        )

        return PresentationResult(
            mode=result.mode,
            request=result.request,
            summary={
                "title": "API-09 parity fixture",
                "top_country": "ISR",
            },
            table=table,
            tables={
                "audit": audit_table,
            },
            metadata=dict(result.metadata),
            diagnostics=dict(result.diagnostics),
            warnings=list(result.warnings),
            messages=[
                AppMessage(
                    level="success",
                    text="Comparison completed.",
                ),
                AppMessage(
                    level="warning",
                    text="Review synthetic warning.",
                    detail="API-09 fixture detail",
                ),
            ],
        )


class _ParityFacade:
    def __init__(
        self,
        comparison_service: _ParityComparisonService,
        presentation_service: _ParityPresentationService,
    ) -> None:
        self.comparison_service = comparison_service
        self.presentation_service = presentation_service

    def compare_single_metric(
        self,
        request: Any,
    ) -> tuple[ComparisonResult, PresentationResult]:
        result = self.comparison_service.run_single_metric(request)

        presentation = self.presentation_service.build_single_metric_presentation(
            result
        )

        return result, presentation


class _TestClientAdapter:
    """Expose FastAPI TestClient through the sync client protocol."""

    def __init__(self, client: TestClient) -> None:
        self.client = client

    def get(
        self,
        url: str,
        *,
        headers: Mapping[str, str] | None = None,
    ) -> Any:
        return self.client.get(
            url,
            headers=dict(headers or {}),
        )

    def post(
        self,
        url: str,
        *,
        json: Any,
        headers: Mapping[str, str] | None = None,
    ) -> Any:
        return self.client.post(
            url,
            json=json,
            headers=dict(headers or {}),
        )


def _all_tables(
    presentation: PresentationResult,
) -> dict[str, pd.DataFrame]:
    tables = dict(presentation.tables)

    if presentation.table is not None:
        tables["main"] = presentation.table

    return tables


def test_api_09_local_and_http_clients_preserve_same_result(
    fake_app_context,
) -> None:
    comparison_service = _ParityComparisonService()
    presentation_service = _ParityPresentationService()

    facade = _ParityFacade(
        comparison_service,
        presentation_service,
    )

    local_client = LocalCountryCompareClient(
        context=fake_app_context,
        facade=facade,  # type: ignore[arg-type]
        services={
            "comparison_service": comparison_service,
            "presentation_service": presentation_service,
        },
    )

    app = create_app(
        settings=ApiSettings(
            max_records=500,
        )
    )

    app.dependency_overrides[get_app_facade] = lambda: facade

    api_test_client = TestClient(app)

    http_client = HttpCountryCompareClient(
        "http://testserver",
        http_client=_TestClientAdapter(api_test_client),
    )

    request_kwargs = {
        "country_codes": ["ISR", "FRA"],
        "metric_id": "gdp_per_capita",
        "year_strategy": "latest_per_metric",
        "top_n": 2,
    }

    local_result = local_client.run_single_metric_comparison(**request_kwargs)

    http_result = http_client.run_single_metric_comparison(**request_kwargs)

    assert isinstance(local_result, PresentationResult)
    assert isinstance(http_result, PresentationResult)

    assert local_result.ok
    assert http_result.ok

    assert http_result.mode == local_result.mode
    assert http_result.summary == local_result.summary
    assert http_result.metadata == local_result.metadata
    assert http_result.diagnostics == local_result.diagnostics
    assert http_result.warnings == local_result.warnings
    assert http_result.messages == local_result.messages

    local_tables = _all_tables(local_result)
    http_tables = _all_tables(http_result)

    assert set(http_tables) == set(local_tables)

    for table_name in local_tables:
        pd.testing.assert_frame_equal(
            http_tables[table_name].reset_index(drop=True),
            local_tables[table_name].reset_index(drop=True),
            check_dtype=False,
        )

    local_presentation_service = local_client.as_ui_services()["presentation_service"]
    http_presentation_service = http_client.as_ui_services()["presentation_service"]

    local_csv = local_presentation_service.export_table_csv_bytes(local_result.table)
    http_csv = http_presentation_service.export_table_csv_bytes(http_result.table)

    assert http_csv == local_csv

    local_bundle = json.loads(
        local_presentation_service.export_presentation_bundle_json_bytes(
            local_result
        ).decode("utf-8")
    )

    http_bundle = json.loads(
        http_presentation_service.export_presentation_bundle_json_bytes(
            http_result
        ).decode("utf-8")
    )

    assert http_bundle == local_bundle
