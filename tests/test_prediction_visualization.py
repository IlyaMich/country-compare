from __future__ import annotations

import pandas as pd
import pytest

from country_compare.prediction import (
    SingleMetricPredictionRequest,
    build_actual_vs_predicted_dataframe,
    build_forecast_table_dataframe,
    build_line_chart_dataframe,
    predict_metric_country_grid,
    predict_single_metric,
    predict_single_metric_for_countries,
)
from country_compare.prediction.visualization import (
    FORECAST_TABLE_COLUMNS,
    LINE_CHART_COLUMNS,
)


def _canonical_df() -> pd.DataFrame:
    rows = []
    values = {
        ("ISR", "gdp_per_capita"): [10.0, 20.0, 30.0],
        ("FRA", "gdp_per_capita"): [10.0, 15.0, 20.0],
        ("ISR", "unemployment_pct"): [8.0, 7.0, 6.0],
        ("FRA", "unemployment_pct"): [9.0, 8.5, 8.0],
    }
    country_names = {"ISR": "Israel", "FRA": "France"}
    metric_meta = {
        "gdp_per_capita": ("GDP per capita", "USD", True, "economy", "https://example.com/gdp"),
        "unemployment_pct": ("Unemployment", "pct", False, "labor", "https://example.com/unemployment"),
    }
    for (country_code, metric_id), series in values.items():
        metric_name, unit, higher_is_better, category, source_url = metric_meta[metric_id]
        for offset, value in enumerate(series):
            rows.append(
                {
                    "country_code": country_code,
                    "country_name": country_names[country_code],
                    "metric_id": metric_id,
                    "metric_name": metric_name,
                    "value": value,
                    "year": 2020 + offset,
                    "unit": unit,
                    "source_name": "Example Source",
                    "source_url": source_url,
                    "higher_is_better": higher_is_better,
                    "category": category,
                    "dataset_version": "test-v1",
                    "region": "Example Region",
                    "income_group": "High income",
                    "notes": None,
                }
            )
    return pd.DataFrame(rows)


def test_line_chart_dataframe_contains_actual_and_forecast_series_labels() -> None:
    result = predict_single_metric(
        _canonical_df(),
        SingleMetricPredictionRequest(
            country_code="ISR",
            metric_id="gdp_per_capita",
            horizon_years=2,
        ),
    )

    chart_df = build_line_chart_dataframe(result)

    assert list(chart_df.columns[: len(LINE_CHART_COLUMNS)]) == list(LINE_CHART_COLUMNS)
    assert chart_df["row_type"].tolist() == [
        "actual",
        "actual",
        "actual",
        "predicted",
        "predicted",
    ]
    assert chart_df["series_label"].tolist() == [
        "Israel actual",
        "Israel actual",
        "Israel actual",
        "Israel forecast",
        "Israel forecast",
    ]
    assert chart_df["overlay_series_label"].unique().tolist() == ["Israel"]
    assert chart_df["year"].tolist() == [2020, 2021, 2022, 2023, 2024]
    assert "series_label" not in result.combined_df.columns


def test_line_chart_dataframe_disambiguates_multiple_countries() -> None:
    result = predict_single_metric_for_countries(
        _canonical_df(),
        metric_id="gdp_per_capita",
        country_codes=["ISR", "FRA"],
        horizon_years=1,
    )

    chart_df = build_line_chart_dataframe(result)

    assert set(chart_df["series_label"].unique().tolist()) == {
        "Israel actual",
        "Israel forecast",
        "France actual",
        "France forecast",
    }
    assert chart_df.loc[
        chart_df["series_label"].eq("France forecast"),
        "value",
    ].tolist() == pytest.approx([25.0])


def test_line_chart_dataframe_disambiguates_country_metric_grid() -> None:
    result = predict_metric_country_grid(
        _canonical_df(),
        country_codes=["ISR", "FRA"],
        metric_ids=["gdp_per_capita", "unemployment_pct"],
        horizon_years=1,
    )

    chart_df = build_line_chart_dataframe(result)

    assert "Israel — GDP per capita actual" in set(chart_df["series_label"].tolist())
    assert "France — Unemployment forecast" in set(chart_df["series_label"].tolist())
    assert "ISR|gdp_per_capita|predicted" in set(chart_df["series_group"].tolist())


def test_actual_vs_predicted_dataframe_uses_shared_overlay_label() -> None:
    result = predict_single_metric(
        _canonical_df(),
        SingleMetricPredictionRequest(
            country_code="ISR",
            metric_id="gdp_per_capita",
            horizon_years=1,
        ),
    )

    overlay_df = build_actual_vs_predicted_dataframe(result)

    assert overlay_df["series_label"].unique().tolist() == ["Israel"]
    assert overlay_df["row_type"].tolist() == ["actual", "actual", "actual", "predicted"]


def test_forecast_table_dataframe_renames_forecast_year_and_predicted_value() -> None:
    result = predict_single_metric_for_countries(
        _canonical_df(),
        metric_id="gdp_per_capita",
        country_codes=["ISR", "FRA"],
        horizon_years=2,
    )

    table_df = build_forecast_table_dataframe(result)

    assert list(table_df.columns[: len(FORECAST_TABLE_COLUMNS)]) == list(FORECAST_TABLE_COLUMNS)
    assert "forecast_year" in table_df.columns
    assert "predicted_value" in table_df.columns
    assert "year" in table_df.columns  # preserved as an extra source column for traceability
    assert table_df["row_type"].eq("predicted").all()
    assert table_df["forecast_year"].tolist() == [2023, 2024, 2023, 2024]
    assert table_df["predicted_value"].tolist() == pytest.approx([40.0, 50.0, 25.0, 30.0])
    assert table_df["forecast_horizon"].tolist() == [1, 2, 1, 2]


def test_visualization_helpers_handle_empty_successful_output_shape() -> None:
    result = predict_single_metric_for_countries(
        _canonical_df(),
        metric_id="gdp_per_capita",
        country_codes=["USA"],
        horizon_years=1,
        fail_fast=False,
    )

    assert result.forecast_df.empty

    chart_df = build_line_chart_dataframe(result)
    table_df = build_forecast_table_dataframe(result)

    assert chart_df.empty
    assert table_df.empty
    assert list(chart_df.columns[: len(LINE_CHART_COLUMNS)]) == list(LINE_CHART_COLUMNS)
    assert list(table_df.columns[: len(FORECAST_TABLE_COLUMNS)]) == list(FORECAST_TABLE_COLUMNS)