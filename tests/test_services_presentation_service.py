from __future__ import annotations

from types import SimpleNamespace

import pandas as pd
import pytest
from matplotlib.figure import Figure

from country_compare.services.presentation_service import PresentationService
from country_compare.services.requests import (
    MultiMetricRequest,
    SingleMetricRequest,
    WeightedScoreRequest,
)
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


def test_build_multi_metric_presentation_builds_long_and_wide_tables(monkeypatch: pytest.MonkeyPatch) -> None:
    dataframe = pd.DataFrame(
        [
            {
                "metric_id": "gdp_per_capita",
                "metric_name": "GDP per capita",
                "country_code": "DEU",
                "country_name": "Germany",
                "value": 67000.0,
                "normalized_value": 1.0,
                "rank": 1,
                "year": 2023,
                "unit": "USD",
                "category": "economy",
                "normalization_method": "minmax",
            },
            {
                "metric_id": "gdp_per_capita",
                "metric_name": "GDP per capita",
                "country_code": "ISR",
                "country_name": "Israel",
                "value": 56000.0,
                "normalized_value": 0.8,
                "rank": 2,
                "year": 2023,
                "unit": "USD",
                "category": "economy",
                "normalization_method": "minmax",
            },
            {
                "metric_id": "life_expectancy",
                "metric_name": "Life expectancy",
                "country_code": "ISR",
                "country_name": "Israel",
                "value": 83.0,
                "normalized_value": 1.0,
                "rank": 1,
                "year": 2023,
                "unit": "years",
                "category": "health",
                "normalization_method": "minmax",
            },
            {
                "metric_id": "life_expectancy",
                "metric_name": "Life expectancy",
                "country_code": "DEU",
                "country_name": "Germany",
                "value": 81.0,
                "normalized_value": 0.7,
                "rank": 2,
                "year": 2023,
                "unit": "years",
                "category": "health",
                "normalization_method": "minmax",
            },
        ]
    )
    long_table = pd.DataFrame([{"metric_id": "gdp_per_capita"}])
    raw_wide_table = pd.DataFrame([{"country_code": "DEU", "gdp_per_capita__value": 67000.0}])
    formatted_wide_table = pd.DataFrame([{"country_code": "DEU", "GDP": 67000.0}])
    chart = Figure()

    import country_compare.comparison.multi_metric as comparison_multi_metric
    import country_compare.output.charts as output_charts
    import country_compare.output.tables as output_tables

    monkeypatch.setattr(output_tables, "make_multi_metric_long_table", lambda *args, **kwargs: long_table)
    monkeypatch.setattr(comparison_multi_metric, "build_multi_metric_wide_table", lambda *args, **kwargs: raw_wide_table)
    monkeypatch.setattr(output_tables, "make_multi_metric_wide_table", lambda *args, **kwargs: formatted_wide_table)
    monkeypatch.setattr(output_charts, "plot_multi_metric_heatmap", lambda *args, **kwargs: chart)

    result = ComparisonResult(
        mode="multi_metric",
        request=MultiMetricRequest(
            countries=["ISR", "DEU"],
            metric_ids=["gdp_per_capita", "life_expectancy"],
            year_strategy="latest_per_metric",
        ),
        dataframe=dataframe,
        metadata={
            "metric_ids": ["gdp_per_capita", "life_expectancy"],
            "metric_labels": {
                "gdp_per_capita": "GDP per capita",
                "life_expectancy": "Life expectancy",
            },
            "selected_countries": ["ISR", "DEU"],
            "year_strategy": "latest_per_metric",
            "target_year": None,
            "result_row_count": 4,
            "countries_returned": ["DEU", "ISR"],
            "metrics_returned": ["gdp_per_capita", "life_expectancy"],
            "years_used": [2023],
            "normalization_methods": ["minmax"],
        },
    )

    service = PresentationService()
    presentation = service.build_multi_metric_presentation(result)

    assert presentation.ok is True
    assert presentation.table.equals(long_table)
    assert presentation.tables["Wide comparison table"].equals(formatted_wide_table)
    assert presentation.chart is chart
    assert presentation.summary["top_country"] == "Israel"
    assert "Selection" in presentation.metadata


def test_build_multi_metric_presentation_returns_error_passthrough() -> None:
    error = SimpleNamespace(
        code="comparison_failed",
        title="Comparison failed",
        user_message="Boom",
        technical_detail="trace",
        field_errors=None,
    )

    service = PresentationService()
    presentation = service.build_multi_metric_presentation(
        ComparisonResult(
            mode="multi_metric",
            request=None,
            error=error,
        )
    )

    assert presentation.ok is False
    assert presentation.error.title == "Comparison failed"


def test_build_weighted_score_presentation_builds_table_and_chart(monkeypatch: pytest.MonkeyPatch) -> None:
    dataframe = pd.DataFrame(
        [
            {
                "country_code": "DEU",
                "country_name": "Germany",
                "weighted_score": 0.95,
                "score_rank": 1,
                "profile_name": "default",
                "missing_data_policy": "renormalize_weights",
                "metric_count_used": 2,
                "metric_count_expected": 2,
                "missing_metric_count": 0,
                "missing_metrics": pd.NA,
                "weight_sum_used": 1.0,
                "year_strategy": "latest_per_metric",
                "score_rank_method": "competition_min",
            },
            {
                "country_code": "ISR",
                "country_name": "Israel",
                "weighted_score": 0.80,
                "score_rank": 2,
                "profile_name": "default",
                "missing_data_policy": "renormalize_weights",
                "metric_count_used": 1,
                "metric_count_expected": 2,
                "missing_metric_count": 1,
                "missing_metrics": "life_expectancy",
                "weight_sum_used": 1.0,
                "year_strategy": "latest_per_metric",
                "score_rank_method": "competition_min",
            },
        ]
    )
    table = pd.DataFrame([{"country_code": "DEU", "weighted_score": 0.95}])
    chart = Figure()

    import country_compare.output.charts as output_charts
    import country_compare.output.tables as output_tables

    monkeypatch.setattr(output_tables, "make_weighted_score_table", lambda *args, **kwargs: table)
    monkeypatch.setattr(output_charts, "plot_weighted_scores", lambda *args, **kwargs: chart)

    result = ComparisonResult(
        mode="weighted_score",
        request=WeightedScoreRequest(
            countries=["ISR", "DEU"],
            profile_name="default",
        ),
        dataframe=dataframe,
        metadata={
            "profile_name": "default",
            "selected_countries": ["ISR", "DEU"],
            "profile_year_strategy": "latest_per_metric",
            "target_year": None,
            "missing_data_policy": "renormalize_weights",
            "resolved_weights": {
                "gdp_per_capita": 0.6,
                "life_expectancy": 0.4,
            },
            "result_row_count": 2,
            "countries_returned": ["DEU", "ISR"],
        },
        warnings=[
            "Some weighted scores were computed with missing metrics. Review the diagnostics and missing-data columns in the result table.",
        ],
    )

    service = PresentationService()
    presentation = service.build_weighted_score_presentation(result)

    assert presentation.ok is True
    assert presentation.table.equals(table)
    assert presentation.chart is chart
    assert presentation.summary["top_country"] == "Germany"
    assert presentation.metadata["Selection"]["Profile"] == "default"
    assert "Resolved profile" in presentation.metadata
    assert any(message.level == "warning" for message in presentation.messages)


def test_build_weighted_score_presentation_returns_error_passthrough() -> None:
    error = SimpleNamespace(
        code="scoring_failed",
        title="Weighted scoring failed",
        user_message="Boom",
        technical_detail="trace",
        field_errors=None,
    )

    service = PresentationService()
    presentation = service.build_weighted_score_presentation(
        ComparisonResult(
            mode="weighted_score",
            request=None,
            error=error,
        )
    )

    assert presentation.ok is False
    assert presentation.error.title == "Weighted scoring failed"