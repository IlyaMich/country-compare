from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import pandas as pd
import streamlit as st

from country_compare.prediction import (
    build_forecast_table_dataframe,
    build_line_chart_dataframe,
)
from country_compare.ui.components.messages import render_app_error


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

    if isinstance(dataframe, pd.DataFrame):
        st.markdown("### Predicted comparison table")
        st.dataframe(dataframe, use_container_width=True, hide_index=True)

    prediction_result = getattr(comparison_result, "prediction_result", None)
    if prediction_result is not None:
        with st.expander("Predicted rows used in comparison", expanded=False):
            st.dataframe(
                build_forecast_table_dataframe(prediction_result),
                use_container_width=True,
                hide_index=True,
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

    actual_vs_predicted_df = getattr(backtest_result, "actual_vs_predicted_df", None)
    if isinstance(actual_vs_predicted_df, pd.DataFrame):
        st.markdown("### Actual vs predicted")
        st.dataframe(actual_vs_predicted_df, use_container_width=True, hide_index=True)

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
                        "status": (
                            getattr(item, "status", None).value
                            if getattr(item, "status", None) is not None
                            else None
                        ),
                        "country_code": getattr(item, "country_code", None),
                        "metric_id": getattr(item, "metric_id", None),
                        "method_requested": getattr(item, "method_requested", None),
                        "method_used": getattr(item, "method_used", None),
                        "fallback_used": getattr(item, "fallback_used", None),
                        "warnings": list(getattr(item, "warnings", []) or []),
                        "errors": [
                            {
                                "code": (
                                    getattr(error, "code", None).value
                                    if getattr(error, "code", None) is not None
                                    else None
                                ),
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


def _render_summary_json(*, summary: Mapping[str, Any], debug: bool) -> None:
    if not summary or not debug:
        return
    with st.expander("Summary JSON", expanded=False):
        st.json(summary)


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
