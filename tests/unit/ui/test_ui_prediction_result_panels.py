from __future__ import annotations

import pandas as pd

from country_compare.ui.components.prediction_result_panels import (
    build_predicted_comparison_chart_dataframe,
    build_predicted_comparison_summary,
    build_streamlit_line_chart_table,
)


def test_build_streamlit_line_chart_table_pivots_long_dataframe() -> None:
    dataframe = pd.DataFrame(
        [
            {"year": 2023, "series_label": "Israel actual", "value": 40.0},
            {"year": 2024, "series_label": "Israel forecast", "value": 45.0},
            {"year": 2023, "series_label": "France actual", "value": 20.0},
            {"year": 2024, "series_label": "France forecast", "value": 22.0},
        ]
    )

    pivot = build_streamlit_line_chart_table(dataframe)

    assert list(pivot.index.tolist()) == [2023, 2024]
    assert "Israel actual" in pivot.columns
    assert pivot.loc[2024, "France forecast"] == 22.0


def test_build_predicted_comparison_summary_uses_rank_column() -> None:
    dataframe = pd.DataFrame(
        [
            {"country_name": "Israel", "score": 88.0, "rank": 2},
            {"country_name": "France", "score": 91.5, "rank": 1},
        ]
    )

    summary = build_predicted_comparison_summary(dataframe)

    assert summary is not None
    assert summary.row_count == 2
    assert summary.top_label == "France"
    assert summary.top_value == 91.5
    assert summary.value_column == "score"
    assert summary.rank_column == "rank"


def test_build_predicted_comparison_summary_falls_back_to_value_sort() -> None:
    dataframe = pd.DataFrame(
        [
            {"country_code": "ISR", "forecast_value": 40.0},
            {"country_code": "FRA", "forecast_value": 42.0},
        ]
    )

    summary = build_predicted_comparison_summary(dataframe)

    assert summary is not None
    assert summary.top_label == "FRA"
    assert summary.top_value == 42.0
    assert summary.value_column == "forecast_value"
    assert summary.rank_column is None


def test_build_predicted_comparison_summary_handles_empty_dataframe() -> None:
    dataframe = pd.DataFrame(columns=["country_name", "score", "rank"])

    assert build_predicted_comparison_summary(dataframe) is None


def test_build_predicted_comparison_chart_dataframe_shapes_top_values() -> None:
    dataframe = pd.DataFrame(
        [
            {"country_name": "Israel", "score": 88.0, "rank": 2},
            {"country_name": "France", "score": 91.5, "rank": 1},
        ]
    )

    chart_dataframe = build_predicted_comparison_chart_dataframe(dataframe)

    assert list(chart_dataframe.index) == ["France", "Israel"]
    assert list(chart_dataframe.columns) == ["score"]
    assert chart_dataframe.loc["France", "score"] == 91.5


def test_build_predicted_comparison_chart_dataframe_handles_missing_value_column() -> (
    None
):
    dataframe = pd.DataFrame(
        [
            {"country_name": "Israel", "rank": 2},
            {"country_name": "France", "rank": 1},
        ]
    )

    chart_dataframe = build_predicted_comparison_chart_dataframe(dataframe)

    assert chart_dataframe.empty
