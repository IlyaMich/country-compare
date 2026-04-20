from __future__ import annotations

from typing import Any

import pandas as pd
import streamlit as st

from country_compare.ui.components.messages import render_app_error, render_messages


def render_single_metric_result(
    presentation: Any | None,
    *,
    debug: bool = False,
) -> None:
    render_comparison_result(
        presentation,
        debug=debug,
        empty_message="Run a single-metric comparison to see results here.",
    )


def render_comparison_result(
    presentation: Any | None,
    *,
    debug: bool = False,
    empty_message: str = "Run a comparison to see results here.",
) -> None:
    if presentation is None:
        st.info(empty_message)
        return

    if getattr(presentation, "error", None) is not None:
        render_app_error(presentation.error, debug=debug)
        return

    render_messages(getattr(presentation, "messages", []))

    summary = getattr(presentation, "summary", {}) or {}
    if summary:
        st.subheader(summary.get("title", "Result"))
        description = summary.get("description")
        if description:
            st.caption(description)
        cols = st.columns(3)
        cols[0].metric("Top item", _string_or_dash(summary.get("top_country")))
        cols[1].metric("Top rank", _string_or_dash(summary.get("top_rank")))
        cols[2].metric("Top value", _string_or_dash(summary.get("top_value")))

    table = getattr(presentation, "table", None)
    if isinstance(table, pd.DataFrame):
        st.markdown("### Main result table")
        st.dataframe(table, use_container_width=True)

    extra_tables = getattr(presentation, "tables", {}) or {}
    if extra_tables:
        st.markdown("### Additional tables")
        for title, dataframe in extra_tables.items():
            if isinstance(dataframe, pd.DataFrame):
                st.markdown(f"**{title}**")
                st.dataframe(dataframe, use_container_width=True)

    chart = getattr(presentation, "chart", None)
    if chart is not None:
        st.markdown("### Chart")
        st.pyplot(chart, use_container_width=True)

    extra_charts = getattr(presentation, "charts", {}) or {}
    if extra_charts:
        st.markdown("### Additional charts")
        for title, figure in extra_charts.items():
            st.markdown(f"**{title}**")
            st.pyplot(figure, use_container_width=True)

    metadata = getattr(presentation, "metadata", {}) or {}
    if metadata:
        st.markdown("### Metadata & details")
        for section_name, section_values in metadata.items():
            with st.expander(section_name, expanded=(section_name == "Selection")):
                if isinstance(section_values, dict):
                    for key, value in section_values.items():
                        st.write(f"**{key}:** {_format_value(value)}")
                else:
                    st.write(_format_value(section_values))

    warnings = getattr(presentation, "warnings", None) or []
    if warnings:
        st.markdown("### Warnings")
        for warning in warnings:
            st.warning(str(warning))

    diagnostics = getattr(presentation, "diagnostics", None) or {}
    if diagnostics and debug:
        with st.expander("Diagnostics"):
            st.json(diagnostics)


def _string_or_dash(value: Any) -> str:
    if value is None or value == "":
        return "—"
    return str(value)


def _format_value(value: Any) -> str:
    if isinstance(value, dict):
        return ", ".join(f"{key}={item}" for key, item in value.items()) if value else "—"
    if isinstance(value, list):
        return ", ".join(str(item) for item in value) if value else "—"
    return _string_or_dash(value)