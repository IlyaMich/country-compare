from __future__ import annotations

import pandas as pd

from country_compare.services.presentation_service import PresentationService
from country_compare.services.requests import SingleMetricRequest
from country_compare.services.results import ComparisonResult


def test_build_single_metric_presentation_uses_result_dataframe() -> None:
    dataframe = pd.DataFrame(
        [
            {
                "rank": 2,
                "country_code": "ISR",
                "country_name": "Israel",
                "metric_name": "GDP per capita",
                "value": 56000.0,
                "normalized_value": 0.5,
                "year": 2023,
                "unit": "USD",
                "normalization_method": "minmax",
            },
            {
                "rank": 1,
                "country_code": "DEU",
                "country_name": "Germany",
                "metric_name": "GDP per capita",
                "value": 67000.0,
                "normalized_value": 1.0,
                "year": 2023,
                "unit": "USD",
                "normalization_method": "minmax",
            },
        ]
    )
    result = ComparisonResult(
        mode="single_metric",
        request=SingleMetricRequest(
            countries=["ISR", "DEU"],
            metric_id="gdp_per_capita",
            year_strategy="latest_per_metric",
        ),
        dataframe=dataframe,
        metadata={
            "metric_id": "gdp_per_capita",
            "metric_display_name": "GDP per capita",
            "selected_countries": ["ISR", "DEU"],
            "year_strategy": "latest_per_metric",
            "years_used": [2023],
            "normalization_methods": ["minmax"],
            "result_row_count": 2,
            "metric_unit": "USD",
            "metric_category": "economy",
        },
    )

    service = PresentationService()
    presentation = service.build_single_metric_presentation(result)

    assert presentation.ok is True
    assert presentation.summary["top_country"] == "Germany"
    assert list(presentation.table.columns)[:3] == ["rank", "country_code", "country_name"]
    assert "Selection" in presentation.metadata


def test_build_single_metric_presentation_returns_error_passthrough() -> None:
    class ErrorObj:
        code = "unexpected_error"
        title = "Comparison failed"
        user_message = "Boom"
        technical_detail = "trace"
        field_errors = None

    service = PresentationService()
    presentation = service.build_single_metric_presentation(
        ComparisonResult(
            mode="single_metric",
            request=None,
            error=ErrorObj(),
        )
    )

    assert presentation.ok is False
    assert presentation.error.title == "Comparison failed"
