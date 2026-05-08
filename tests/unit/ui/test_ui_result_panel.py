from __future__ import annotations

import pandas as pd

from country_compare.ui.components.result_panels import (
    build_comparison_chart_dataframe,
    build_comparison_table_summary,
    build_display_extra_tables,
    build_multi_metric_comparison_chart_dataframe,
)


def test_build_comparison_table_summary_uses_rank_column() -> None:
    dataframe = pd.DataFrame(
        [
            {"country_name": "Israel", "score": 88.0, "rank": 2},
            {"country_name": "France", "score": 91.5, "rank": 1},
        ]
    )

    summary = build_comparison_table_summary(dataframe)

    assert summary is not None
    assert summary.row_count == 2
    assert summary.top_label == "France"
    assert summary.top_value == 91.5
    assert summary.value_column == "score"
    assert summary.rank_column == "rank"


def test_build_comparison_table_summary_falls_back_to_value_sort() -> None:
    dataframe = pd.DataFrame(
        [
            {"country_code": "ISR", "value": 40.0},
            {"country_code": "FRA", "value": 42.0},
        ]
    )

    summary = build_comparison_table_summary(dataframe)

    assert summary is not None
    assert summary.top_label == "FRA"
    assert summary.top_value == 42.0
    assert summary.value_column == "value"
    assert summary.rank_column is None


def test_build_comparison_table_summary_handles_empty_dataframe() -> None:
    dataframe = pd.DataFrame(columns=["country_name", "score", "rank"])

    assert build_comparison_table_summary(dataframe) is None


def test_build_comparison_chart_dataframe_shapes_ranked_values() -> None:
    dataframe = pd.DataFrame(
        [
            {"country_name": "Israel", "score": 88.0, "rank": 2},
            {"country_name": "France", "score": 91.5, "rank": 1},
        ]
    )

    chart_dataframe = build_comparison_chart_dataframe(dataframe)

    assert list(chart_dataframe.index) == ["France", "Israel"]
    assert list(chart_dataframe.columns) == ["score"]
    assert chart_dataframe.loc["France", "score"] == 91.5


def test_build_comparison_chart_dataframe_limits_rows() -> None:
    dataframe = pd.DataFrame(
        [
            {"country_name": "A", "score": 5.0},
            {"country_name": "B", "score": 4.0},
            {"country_name": "C", "score": 3.0},
        ]
    )

    chart_dataframe = build_comparison_chart_dataframe(dataframe, max_rows=2)

    assert list(chart_dataframe.index) == ["A", "B"]


def test_build_comparison_chart_dataframe_handles_missing_value_column() -> None:
    dataframe = pd.DataFrame(
        [
            {"country_name": "Israel", "rank": 2},
            {"country_name": "France", "rank": 1},
        ]
    )

    chart_dataframe = build_comparison_chart_dataframe(dataframe)

    assert chart_dataframe.empty


def test_build_display_extra_tables_omits_duplicate_http_main_table() -> None:
    table = pd.DataFrame(
        [
            {"country_code": "DEU", "value": 10},
            {"country_code": "FRA", "value": 8},
        ]
    )

    extra_tables = build_display_extra_tables(
        {"main": table.copy()},
        primary_table=table,
    )

    assert extra_tables == {}


def test_build_display_extra_tables_keeps_distinct_extra_tables() -> None:
    table = pd.DataFrame([{"country_code": "DEU", "value": 10}])
    wide_table = pd.DataFrame([{"country_code": "DEU", "gdp": 10}])

    extra_tables = build_display_extra_tables(
        {"Wide comparison table": wide_table},
        primary_table=table,
    )

    assert list(extra_tables) == ["Wide comparison table"]
    assert extra_tables["Wide comparison table"].equals(wide_table)


def test_build_multi_metric_comparison_chart_dataframe_pivots_long_rows() -> None:
    dataframe = pd.DataFrame(
        [
            {"country_name": "Israel", "metric_name": "GDP", "value": 100.0},
            {"country_name": "Israel", "metric_name": "Life expectancy", "value": 82.0},
            {"country_name": "France", "metric_name": "GDP", "value": 120.0},
            {"country_name": "France", "metric_name": "Life expectancy", "value": 83.0},
        ]
    )

    chart_dataframe = build_multi_metric_comparison_chart_dataframe(dataframe)

    assert list(chart_dataframe.columns) == ["GDP", "Life expectancy"]
    assert chart_dataframe.loc["France", "GDP"] == 120.0
    assert chart_dataframe.loc["Israel", "Life expectancy"] == 82.0


def test_build_multi_metric_comparison_chart_dataframe_uses_wide_numeric_columns() -> (
    None
):
    dataframe = pd.DataFrame(
        [
            {"country_code": "ISR", "gdp_per_capita": 55.0, "life_expectancy": 82.0},
            {"country_code": "FRA", "gdp_per_capita": 48.0, "life_expectancy": 83.0},
        ]
    )

    chart_dataframe = build_multi_metric_comparison_chart_dataframe(dataframe)

    assert list(chart_dataframe.index) == ["ISR", "FRA"]
    assert list(chart_dataframe.columns) == ["gdp_per_capita", "life_expectancy"]
    assert chart_dataframe.loc["FRA", "life_expectancy"] == 83.0


def test_build_multi_metric_comparison_chart_dataframe_ignores_single_score_shape() -> (
    None
):
    dataframe = pd.DataFrame(
        [
            {"country_name": "Israel", "score": 88.0, "rank": 2},
            {"country_name": "France", "score": 91.5, "rank": 1},
        ]
    )

    chart_dataframe = build_multi_metric_comparison_chart_dataframe(dataframe)

    assert chart_dataframe.empty
