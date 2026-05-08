from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

import pandas as pd
import streamlit as st

from country_compare.prediction import (
    build_forecast_table_dataframe,
    build_line_chart_dataframe,
)
from country_compare.ui import text as ui_text
from country_compare.ui.components.downloads import (
    build_result_markdown_summary,
    render_result_downloads,
)
from country_compare.ui.components.messages import render_app_error
from country_compare.ui.components.prediction_quality import (
    render_prediction_quality_panel,
)

PREDICTED_COMPARISON_LABEL_COLUMNS = (
    "country_name",
    "country_code",
    "metric_name",
    "metric_id",
    "profile_name",
)

PREDICTED_COMPARISON_VALUE_COLUMNS = (
    "score",
    "forecast_value",
    "predicted_value",
    "value",
    "metric_value",
)

PREDICTED_COMPARISON_RANK_COLUMNS = (
    "rank",
    "overall_rank",
    "score_rank",
)

BACKTEST_YEAR_COLUMNS = (
    "year",
    "test_year",
    "forecast_year",
    "prediction_year",
)

BACKTEST_ACTUAL_COLUMNS = (
    "actual_value",
    "actual",
    "observed_value",
    "observed",
    "value",
)

BACKTEST_PREDICTED_COLUMNS = (
    "predicted_value",
    "predicted",
    "prediction",
    "forecast_value",
    "forecast",
)


@dataclass(frozen=True)
class PredictedComparisonSummary:
    row_count: int
    top_label: str
    top_value: object | None
    label_column: str | None
    value_column: str | None
    rank_column: str | None


def build_predicted_comparison_summary(
    dataframe: pd.DataFrame,
) -> PredictedComparisonSummary | None:
    if dataframe.empty:
        return None

    label_column = _first_existing_column(dataframe, PREDICTED_COMPARISON_LABEL_COLUMNS)
    value_column = _first_existing_column(dataframe, PREDICTED_COMPARISON_VALUE_COLUMNS)
    rank_column = _first_existing_column(dataframe, PREDICTED_COMPARISON_RANK_COLUMNS)

    sorted_dataframe = _sort_predicted_comparison_dataframe(
        dataframe=dataframe,
        rank_column=rank_column,
        value_column=value_column,
    )

    if sorted_dataframe.empty:
        return None

    top_row = sorted_dataframe.iloc[0]

    return PredictedComparisonSummary(
        row_count=int(len(dataframe.index)),
        top_label=_row_label(top_row, label_column, fallback_position=1),
        top_value=(
            _cell_value(top_row, value_column) if value_column is not None else None
        ),
        label_column=label_column,
        value_column=value_column,
        rank_column=rank_column,
    )


def build_predicted_comparison_chart_dataframe(
    dataframe: pd.DataFrame,
    *,
    max_rows: int = 10,
) -> pd.DataFrame:
    if dataframe.empty:
        return pd.DataFrame()

    value_column = _first_existing_column(dataframe, PREDICTED_COMPARISON_VALUE_COLUMNS)
    rank_column = _first_existing_column(dataframe, PREDICTED_COMPARISON_RANK_COLUMNS)
    label_column = _first_existing_column(dataframe, PREDICTED_COMPARISON_LABEL_COLUMNS)

    if value_column is None:
        return pd.DataFrame()

    sorted_dataframe = _sort_predicted_comparison_dataframe(
        dataframe=dataframe,
        rank_column=rank_column,
        value_column=value_column,
    ).head(max_rows)

    values = pd.to_numeric(sorted_dataframe[value_column], errors="coerce")
    labels = _make_unique_labels(
        [
            _row_label(row, label_column, fallback_position=position + 1)
            for position, (_, row) in enumerate(sorted_dataframe.iterrows())
        ]
    )

    chart_dataframe = pd.DataFrame(
        {str(value_column): values.to_list()},
        index=labels,
    )

    return chart_dataframe.dropna()


def _render_predicted_comparison_summary_panel(dataframe: pd.DataFrame) -> None:
    summary = build_predicted_comparison_summary(dataframe)

    st.markdown(f"### {ui_text.RANKED_COMPARISON_SUMMARY_HEADING}")

    if summary is None:
        st.info(ui_text.PREDICTED_COMPARISON_NO_RANKED_ROWS_MESSAGE)
        return

    cols = st.columns(3)
    cols[0].metric(ui_text.RANKED_ROWS_METRIC_LABEL, _metric_value(summary.row_count))
    cols[1].metric(ui_text.TOP_RESULT_METRIC_LABEL, summary.top_label)
    cols[2].metric(ui_text.TOP_VALUE_METRIC_LABEL, _metric_value(summary.top_value))

    chart_dataframe = build_predicted_comparison_chart_dataframe(dataframe)
    if chart_dataframe.empty:
        st.caption(ui_text.COMPARISON_NO_NUMERIC_VALUE_MESSAGE)
        return

    st.bar_chart(chart_dataframe)


def _sort_predicted_comparison_dataframe(
    *,
    dataframe: pd.DataFrame,
    rank_column: str | None,
    value_column: str | None,
) -> pd.DataFrame:
    working = dataframe.copy()

    if rank_column is not None:
        working["_comparison_rank_order"] = pd.to_numeric(
            working[rank_column],
            errors="coerce",
        )
        return working.sort_values(
            "_comparison_rank_order",
            na_position="last",
        ).drop(columns=["_comparison_rank_order"])

    if value_column is not None:
        working["_comparison_value_order"] = pd.to_numeric(
            working[value_column],
            errors="coerce",
        )
        return working.sort_values(
            "_comparison_value_order",
            ascending=False,
            na_position="last",
        ).drop(columns=["_comparison_value_order"])

    return working


def _first_existing_column(
    dataframe: pd.DataFrame,
    candidates: tuple[str, ...],
) -> str | None:
    for column in candidates:
        if column in dataframe.columns:
            return column
    return None


def _row_label(
    row: pd.Series,
    label_column: str | None,
    *,
    fallback_position: int,
) -> str:
    if label_column is not None:
        label = _safe_string(row.get(label_column))
        if label is not None:
            return label

    country_name = _safe_string(row.get("country_name"))
    country_code = _safe_string(row.get("country_code"))
    metric_name = _safe_string(row.get("metric_name"))
    metric_id = _safe_string(row.get("metric_id"))

    label_parts = [
        part
        for part in (country_name or country_code, metric_name or metric_id)
        if part
    ]

    if label_parts:
        return " — ".join(label_parts)

    return f"Result {fallback_position}"


def _make_unique_labels(labels: list[str]) -> list[str]:
    seen: dict[str, int] = {}
    unique_labels: list[str] = []

    for label in labels:
        count = seen.get(label, 0) + 1
        seen[label] = count
        unique_labels.append(label if count == 1 else f"{label} ({count})")

    return unique_labels


def _cell_value(row: pd.Series, column: str) -> object | None:
    value = row.get(column)
    if value is None:
        return None
    if pd.isna(value):
        return None
    return value


def _safe_string(value: object | None) -> str | None:
    if value is None:
        return None
    if pd.isna(value):
        return None

    text = str(value).strip()
    return text or None


def render_prediction_service_result(
    result: Any | None,
    *,
    debug: bool = False,
    empty_message: str = "Run a prediction to see results here.",
) -> None:
    if result is None:
        st.info(empty_message)
        return

    error = getattr(result, "error", None)
    if error is not None:
        render_app_error(error, debug=debug)
        return

    warnings = list(getattr(result, "warnings", []) or [])
    for warning in warnings:
        st.warning(str(warning))

    mode = str(getattr(result, "mode", "prediction") or "prediction")
    summary = getattr(result, "summary", {}) or {}

    if getattr(result, "prediction_result", None) is not None:
        _render_prediction_result_body(result, mode=mode, summary=summary, debug=debug)
        return

    if getattr(result, "predicted_comparison_result", None) is not None:
        _render_predicted_comparison_body(
            result, mode=mode, summary=summary, debug=debug
        )
        return

    if getattr(result, "backtest_result", None) is not None:
        _render_backtest_body(result, mode=mode, summary=summary, debug=debug)
        return

    dataframe = getattr(result, "dataframe", None)
    if isinstance(dataframe, pd.DataFrame):
        st.dataframe(dataframe, use_container_width=True, hide_index=True)

    _render_summary_json(summary=summary, debug=debug)


def render_prediction_catalog_summary(
    methods: list[dict[str, Any]], *, debug: bool = False
) -> None:
    if not methods:
        st.info("No prediction methods are currently available.")
        return

    st.write("**Available methods**")
    st.dataframe(
        pd.DataFrame(methods),
        use_container_width=True,
        hide_index=True,
    )

    if debug:
        with st.expander("Method catalog JSON", expanded=False):
            st.json(methods)


def build_streamlit_line_chart_table(dataframe: pd.DataFrame) -> pd.DataFrame:
    if dataframe.empty or not {"year", "series_label", "value"}.issubset(
        dataframe.columns
    ):
        return pd.DataFrame()

    chart_df = dataframe.copy(deep=True)
    chart_df["year"] = pd.to_numeric(chart_df["year"], errors="coerce").astype("Int64")
    chart_df["value"] = pd.to_numeric(chart_df["value"], errors="coerce")
    chart_df = chart_df.dropna(subset=["year", "value", "series_label"])
    if chart_df.empty:
        return pd.DataFrame()

    pivot = chart_df.pivot_table(
        index="year",
        columns="series_label",
        values="value",
        aggfunc="first",
    ).sort_index()
    return pivot.copy(deep=True)


def build_backtest_line_chart_dataframe(dataframe: pd.DataFrame) -> pd.DataFrame:
    if dataframe.empty:
        return pd.DataFrame()

    year_column = _first_existing_column(dataframe, BACKTEST_YEAR_COLUMNS)
    actual_column = _first_existing_column(dataframe, BACKTEST_ACTUAL_COLUMNS)
    predicted_column = _first_existing_column(dataframe, BACKTEST_PREDICTED_COLUMNS)

    if (
        year_column is None
        or actual_column is None
        or predicted_column is None
        or actual_column == predicted_column
    ):
        return pd.DataFrame()

    working = dataframe[[year_column, actual_column, predicted_column]].copy()
    working[year_column] = pd.to_numeric(working[year_column], errors="coerce")
    working[actual_column] = pd.to_numeric(working[actual_column], errors="coerce")
    working[predicted_column] = pd.to_numeric(
        working[predicted_column],
        errors="coerce",
    )
    working = working.dropna(subset=[year_column])
    working = working.dropna(
        subset=[actual_column, predicted_column],
        how="all",
    )

    if working.empty:
        return pd.DataFrame()

    working[year_column] = working[year_column].astype(int)
    chart_dataframe = pd.DataFrame(
        {
            "Actual": working[actual_column].to_list(),
            "Predicted": working[predicted_column].to_list(),
        },
        index=working[year_column].to_list(),
    )
    chart_dataframe = chart_dataframe.groupby(level=0).first().sort_index()

    return chart_dataframe.dropna(axis="columns", how="all")


def _render_prediction_result_body(
    result: Any, *, mode: str, summary: Mapping[str, Any], debug: bool
) -> None:
    prediction_result = result.prediction_result
    forecast_table_df = build_forecast_table_dataframe(prediction_result)
    line_chart_df = build_line_chart_dataframe(prediction_result)
    line_chart_table = build_streamlit_line_chart_table(line_chart_df)

    _render_prediction_metrics(
        mode=mode, summary=summary, metadata=getattr(prediction_result, "metadata", {})
    )
    render_prediction_quality_panel(
        diagnostics=getattr(prediction_result, "diagnostics", []),
        summary=summary,
        mode=mode,
    )

    if not forecast_table_df.empty:
        st.markdown("### Forecast table")
        st.dataframe(forecast_table_df, use_container_width=True, hide_index=True)
    else:
        st.info("No forecast rows were returned.")

    if not line_chart_table.empty:
        st.markdown("### Actual vs forecast")
        st.line_chart(line_chart_table)

    with st.expander("Underlying series data", expanded=False):
        combined_df = getattr(prediction_result, "combined_df", None)
        if isinstance(combined_df, pd.DataFrame) and not combined_df.empty:
            st.dataframe(combined_df, use_container_width=True, hide_index=True)
        else:
            st.write("No combined actual/forecast dataframe is available.")
    _render_prediction_downloads(
        table=forecast_table_df if not forecast_table_df.empty else None,
        diagnostics={
            "mode": mode,
            "summary": summary,
            "metadata": getattr(prediction_result, "metadata", {}),
            "diagnostics": getattr(prediction_result, "diagnostics", []),
        },
        title="Country Compare Prediction Result",
        base_file_name=f"country_compare_{mode}_forecast",
        key_prefix=f"prediction_{mode}",
        notes=[
            "Forecasts are baseline statistical projections, not precise predictions.",
            "Review diagnostics before using forecast outputs.",
        ],
    )
    _render_diagnostics(
        diagnostics=getattr(prediction_result, "diagnostics", []),
        summary=summary,
        debug=debug,
    )


def _render_predicted_comparison_body(
    result: Any, *, mode: str, summary: Mapping[str, Any], debug: bool
) -> None:
    comparison_result = result.predicted_comparison_result
    dataframe = getattr(result, "dataframe", None)
    selected_year = summary.get("selected_forecast_year")
    selected_horizon = summary.get("selected_forecast_horizon")

    prediction_result = getattr(comparison_result, "prediction_result", None)
    failed_series_count = None
    if prediction_result is not None:
        failed_series_count = getattr(prediction_result, "metadata", {}).get(
            "failed_series_count"
        )
    if failed_series_count is None:
        failed_series_count = summary.get("failed_series_count")

    cols = st.columns(4)
    cols[0].metric("Rows", _metric_value(_row_count(dataframe)))
    cols[1].metric("Forecast year", _metric_value(selected_year))
    cols[2].metric("Forecast horizon", _metric_value(selected_horizon))
    cols[3].metric("Failed series", _metric_value(failed_series_count))

    render_prediction_quality_panel(
        diagnostics=getattr(comparison_result, "diagnostics", []),
        summary=summary,
        mode=mode,
    )

    if isinstance(dataframe, pd.DataFrame):
        _render_predicted_comparison_summary_panel(dataframe)

        st.markdown(f"### {ui_text.PREDICTED_COMPARISON_TABLE_HEADING}")
        st.dataframe(dataframe, use_container_width=True, hide_index=True)
    else:
        st.info("No predicted comparison rows were returned.")

    if prediction_result is not None:
        with st.expander("Predicted rows used in comparison", expanded=False):
            st.dataframe(
                build_forecast_table_dataframe(prediction_result),
                use_container_width=True,
                hide_index=True,
            )

    _render_prediction_downloads(
        table=dataframe if isinstance(dataframe, pd.DataFrame) else None,
        diagnostics={
            "mode": mode,
            "summary": summary,
            "metadata": getattr(comparison_result, "metadata", {}),
            "diagnostics": getattr(comparison_result, "diagnostics", []),
        },
        title="Country Compare Predicted Comparison Result",
        base_file_name=f"country_compare_{mode}",
        key_prefix=f"prediction_{mode}",
        notes=[
            "This comparison ranks forecasted rows for the selected forecast year or horizon.",
            "Review diagnostics before using predicted comparison outputs.",
        ],
    )
    _render_diagnostics(
        diagnostics=getattr(comparison_result, "diagnostics", []),
        summary=summary,
        debug=debug,
    )


def _render_backtest_body(
    result: Any, *, mode: str, summary: Mapping[str, Any], debug: bool
) -> None:
    backtest_result = result.backtest_result
    metrics = dict(
        summary.get("metrics") or getattr(backtest_result, "metrics", {}) or {}
    )

    cols = st.columns(4)
    cols[0].metric("Method used", _metric_value(metrics.get("method_used")))
    cols[1].metric("MAE", _metric_value(metrics.get("mae")))
    cols[2].metric("RMSE", _metric_value(metrics.get("rmse")))
    cols[3].metric("MAPE", _metric_value(metrics.get("mape")))

    secondary_cols = st.columns(4)
    secondary_cols[0].metric(
        "Train years", _year_range_text(metrics, "train_start_year", "train_end_year")
    )
    secondary_cols[1].metric(
        "Test years", _year_range_text(metrics, "test_start_year", "test_end_year")
    )
    secondary_cols[2].metric(
        "Train observations", _metric_value(metrics.get("n_train_observations"))
    )
    secondary_cols[3].metric(
        "Test observations", _metric_value(metrics.get("n_test_observations"))
    )

    render_prediction_quality_panel(
        diagnostics=getattr(backtest_result, "diagnostics", []),
        summary=summary,
        mode=mode,
    )

    actual_vs_predicted_df = getattr(backtest_result, "actual_vs_predicted_df", None)
    if isinstance(actual_vs_predicted_df, pd.DataFrame):
        st.markdown("### Actual vs predicted")
        backtest_chart_dataframe = build_backtest_line_chart_dataframe(
            actual_vs_predicted_df
        )
        if not backtest_chart_dataframe.empty:
            st.line_chart(backtest_chart_dataframe)
        else:
            st.caption("No chartable actual-vs-predicted series is available.")

        st.dataframe(actual_vs_predicted_df, use_container_width=True, hide_index=True)

    _render_prediction_downloads(
        table=(
            actual_vs_predicted_df
            if isinstance(actual_vs_predicted_df, pd.DataFrame)
            else None
        ),
        diagnostics={
            "mode": mode,
            "summary": summary,
            "metrics": metrics,
            "diagnostics": getattr(backtest_result, "diagnostics", []),
        },
        title="Country Compare Backtest Result",
        base_file_name=f"country_compare_{mode}",
        key_prefix=f"prediction_{mode}",
        notes=[
            "Backtests evaluate a forecast method against held-out observed years.",
            "Lower error values indicate a better fit for this historical split.",
        ],
    )
    _render_diagnostics(
        diagnostics=getattr(backtest_result, "diagnostics", []),
        summary=summary,
        debug=debug,
    )


def _render_prediction_metrics(
    *, mode: str, summary: Mapping[str, Any], metadata: Mapping[str, Any]
) -> None:
    forecast_summary = dict(summary.get("forecast") or {})
    diagnostics_summary = dict(summary.get("diagnostics") or {})
    status_counts = dict(diagnostics_summary.get("status_counts") or {})

    method_used = metadata.get("method_used") or summary.get("method_used")
    if method_used is None:
        forecaster_info = summary.get("forecaster_info")
        if isinstance(forecaster_info, list) and forecaster_info:
            method_used = forecaster_info[0].get("method_id")

    cols = st.columns(4)
    cols[0].metric("Forecast rows", _metric_value(forecast_summary.get("row_count")))
    cols[1].metric("Method", _metric_value(method_used))
    cols[2].metric(
        "Successful series",
        _metric_value(
            metadata.get(
                "successful_series_count", forecast_summary.get("series_count")
            )
        ),
    )
    cols[3].metric(
        "Failed series",
        _metric_value(metadata.get("failed_series_count", status_counts.get("failed"))),
    )

    forecast_years = summary.get("forecast_years") or []
    if forecast_years:
        st.caption("Forecast years: " + ", ".join(str(year) for year in forecast_years))


def _render_diagnostics(
    *, diagnostics: list[Any], summary: Mapping[str, Any], debug: bool
) -> None:
    diagnostics_summary = summary.get("diagnostics")
    has_diagnostics = bool(diagnostics) or bool(diagnostics_summary)
    if not has_diagnostics:
        return

    with st.expander("Diagnostics", expanded=False):
        if diagnostics_summary:
            st.write("**Summary**")
            st.json(diagnostics_summary)
        if diagnostics:
            st.write("**Per-series diagnostics**")
            st.json(
                [
                    {
                        "status": _enum_value(getattr(item, "status", None)),
                        "country_code": getattr(item, "country_code", None),
                        "metric_id": getattr(item, "metric_id", None),
                        "method_requested": getattr(item, "method_requested", None),
                        "method_used": getattr(item, "method_used", None),
                        "fallback_used": getattr(item, "fallback_used", None),
                        "warnings": list(getattr(item, "warnings", []) or []),
                        "errors": [
                            {
                                "code": _enum_value(getattr(error, "code", None)),
                                "message": getattr(error, "message", None),
                                "details": getattr(error, "details", None),
                            }
                            for error in list(getattr(item, "errors", []) or [])
                        ],
                    }
                    for item in diagnostics
                ]
            )
        elif debug:
            st.json(summary)


def _render_prediction_downloads(
    *,
    table: pd.DataFrame | None,
    diagnostics: Any | None,
    title: str,
    base_file_name: str,
    key_prefix: str,
    notes: list[str],
) -> None:
    row_count = len(table.index) if isinstance(table, pd.DataFrame) else 0
    column_count = len(table.columns) if isinstance(table, pd.DataFrame) else 0

    summary_markdown = build_result_markdown_summary(
        title=title,
        sections={
            "Result": [
                f"Rows: {row_count}",
                f"Columns: {column_count}",
            ],
            "Notes": notes,
        },
    )

    render_result_downloads(
        table=table,
        diagnostics=diagnostics,
        summary_markdown=summary_markdown,
        base_file_name=base_file_name,
        key_prefix=key_prefix,
    )


def _render_summary_json(*, summary: Mapping[str, Any], debug: bool) -> None:
    if not summary or not debug:
        return
    with st.expander("Summary JSON", expanded=False):
        st.json(summary)


def _enum_value(value: Any) -> Any:
    return getattr(value, "value", value)


def _row_count(dataframe: Any) -> int | None:
    if isinstance(dataframe, pd.DataFrame):
        return int(len(dataframe.index))
    return None


def _metric_value(value: Any) -> str:
    if value is None or value == "":
        return "—"
    if isinstance(value, float):
        return f"{value:.4g}"
    return str(value)


def _year_range_text(metrics: Mapping[str, Any], start_key: str, end_key: str) -> str:
    start = metrics.get(start_key)
    end = metrics.get(end_key)
    if start is None and end is None:
        return "—"
    if start == end:
        return str(start)
    return f"{start}–{end}"
