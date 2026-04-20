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
    if presentation is None:
        st.info("Run a single-metric comparison to see results here.")
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
        cols[0].metric("Top country", _string_or_dash(summary.get("top_country")))
        cols[1].metric("Top rank", _string_or_dash(summary.get("top_rank")))
        cols[2].metric("Top value", _string_or_dash(summary.get("top_value")))

    table = getattr(presentation, "table", None)
    if isinstance(table, pd.DataFrame):
        st.markdown("### Main result table")
        st.dataframe(table, use_container_width=True)

    chart = getattr(presentation, "chart", None)
    if chart is not None:
        st.markdown("### Chart")
        st.pyplot(chart, use_container_width=True)

    metadata = getattr(presentation, "metadata", {}) or {}
    if metadata:
        st.markdown("### Metadata & details")
        for section_name, section_values in metadata.items():
            with st.expander(section_name, expanded=(section_name == "Selection")):
                for key, value in (section_values or {}).items():
                    st.write(f"**{key}:** {_format_value(value)}")

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
    if isinstance(value, list):
        return ", ".join(str(item) for item in value) if value else "—"
    return _string_or_dash(value)
