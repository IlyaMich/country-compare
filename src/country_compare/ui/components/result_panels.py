from __future__ import annotations

from typing import Any

import pandas as pd
import streamlit as st

from country_compare.ui.components.downloads import (
    build_result_markdown_summary,
    render_result_downloads,
)
from country_compare.ui.components.export_controls import render_presentation_exports
from country_compare.ui.components.messages import render_app_error, render_messages


def render_single_metric_result(
    presentation: Any | None,
    *,
    debug: bool = False,
    presentation_service: Any | None = None,
) -> None:
    render_comparison_result(
        presentation,
        debug=debug,
        presentation_service=presentation_service,
        empty_message="Run a single-metric comparison to see results here.",
    )


def render_comparison_result(
    presentation: Any | None,
    *,
    debug: bool = False,
    presentation_service: Any | None = None,
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

    _render_comparison_downloads(presentation, table=table, summary=summary)

    if presentation_service is not None:
        render_presentation_exports(
            presentation,
            presentation_service=presentation_service,
            debug=debug,
            key_prefix=f"result_{getattr(presentation, 'mode', 'comparison')}",
        )

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


def _render_comparison_downloads(
    presentation: Any,
    *,
    table: Any,
    summary: dict[str, Any],
) -> None:
    if not isinstance(table, pd.DataFrame):
        return

    mode = str(getattr(presentation, "mode", "comparison") or "comparison")
    metadata = getattr(presentation, "metadata", {}) or {}
    warnings = list(getattr(presentation, "warnings", []) or [])
    diagnostics = getattr(presentation, "diagnostics", {}) or {}

    summary_markdown = build_result_markdown_summary(
        title=str(summary.get("title", "Country Compare Result")),
        sections={
            "Result": [
                f"Mode: {mode}",
                f"Rows: {len(table.index)}",
                f"Columns: {len(table.columns)}",
                f"Top item: {_string_or_dash(summary.get('top_country'))}",
                f"Top rank: {_string_or_dash(summary.get('top_rank'))}",
            ],
            "Notes": "Generated from the current Country Compare UI selection.",
        },
    )

    render_result_downloads(
        table=table,
        diagnostics={
            "mode": mode,
            "summary": summary,
            "metadata": metadata,
            "warnings": warnings,
            "diagnostics": diagnostics,
        },
        summary_markdown=summary_markdown,
        base_file_name=f"country_compare_{mode}_result",
        key_prefix=f"comparison_{mode}",
    )


def _string_or_dash(value: Any) -> str:
    if value is None or value == "":
        return "—"
    return str(value)


def _format_value(value: Any) -> str:
    if isinstance(value, dict):
        return (
            ", ".join(f"{key}={item}" for key, item in value.items()) if value else "—"
        )
    if isinstance(value, list):
        return ", ".join(str(item) for item in value) if value else "—"
    return _string_or_dash(value)
