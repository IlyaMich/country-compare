from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pandas as pd
import streamlit as st

from country_compare.ui.components.downloads import (
    build_result_markdown_summary,
    render_result_downloads,
)
from country_compare.ui.components.export_controls import render_presentation_exports
from country_compare.ui.components.messages import render_app_error, render_messages

COMPARISON_LABEL_COLUMNS = (
    "country_name",
    "country",
    "country_code",
    "metric_name",
    "metric_display_name",
    "metric_id",
    "profile_name",
)

COMPARISON_VALUE_COLUMNS = (
    "score",
    "weighted_score",
    "normalized_score",
    "value",
    "metric_value",
    "latest_value",
)

COMPARISON_RANK_COLUMNS = (
    "rank",
    "overall_rank",
    "score_rank",
)


@dataclass(frozen=True)
class ComparisonTableSummary:
    row_count: int
    top_label: str
    top_value: object | None
    label_column: str | None
    value_column: str | None
    rank_column: str | None


def build_comparison_table_summary(
    dataframe: pd.DataFrame,
) -> ComparisonTableSummary | None:
    if dataframe.empty:
        return None

    label_column = _first_existing_column(dataframe, COMPARISON_LABEL_COLUMNS)
    value_column = _first_existing_column(dataframe, COMPARISON_VALUE_COLUMNS)
    rank_column = _first_existing_column(dataframe, COMPARISON_RANK_COLUMNS)

    sorted_dataframe = _sort_comparison_dataframe(
        dataframe=dataframe,
        rank_column=rank_column,
        value_column=value_column,
    )
    if sorted_dataframe.empty:
        return None

    top_row = sorted_dataframe.iloc[0]

    return ComparisonTableSummary(
        row_count=int(len(dataframe.index)),
        top_label=_row_label(top_row, label_column, fallback_position=1),
        top_value=_cell_value(top_row, value_column) if value_column else None,
        label_column=label_column,
        value_column=value_column,
        rank_column=rank_column,
    )


def build_comparison_chart_dataframe(
    dataframe: pd.DataFrame,
    *,
    max_rows: int = 10,
) -> pd.DataFrame:
    if dataframe.empty:
        return pd.DataFrame()

    label_column = _first_existing_column(dataframe, COMPARISON_LABEL_COLUMNS)
    value_column = _first_existing_column(dataframe, COMPARISON_VALUE_COLUMNS)
    rank_column = _first_existing_column(dataframe, COMPARISON_RANK_COLUMNS)

    if value_column is None:
        return pd.DataFrame()

    sorted_dataframe = _sort_comparison_dataframe(
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


def _render_comparison_summary_panel(dataframe: pd.DataFrame) -> None:
    summary = build_comparison_table_summary(dataframe)
    chart_dataframe = build_comparison_chart_dataframe(dataframe)

    if summary is None and chart_dataframe.empty:
        return

    st.markdown("### Comparison summary")

    if summary is not None:
        cols = st.columns(3)
        cols[0].metric("Compared rows", _string_or_dash(summary.row_count))
        cols[1].metric("Top result", summary.top_label)
        cols[2].metric("Top value", _string_or_dash(summary.top_value))

    if not chart_dataframe.empty:
        st.bar_chart(chart_dataframe)
    else:
        st.caption("No numeric comparison value was available for a visual summary.")


def _sort_comparison_dataframe(
    *,
    dataframe: pd.DataFrame,
    rank_column: str | None,
    value_column: str | None,
) -> pd.DataFrame:
    working = dataframe.copy()

    if rank_column is not None:
        rank_order = pd.to_numeric(working[rank_column], errors="coerce")
        if rank_order.notna().any():
            working["_comparison_rank_order"] = rank_order
            return working.sort_values(
                "_comparison_rank_order",
                na_position="last",
            ).drop(columns=["_comparison_rank_order"])

    if value_column is not None:
        value_order = pd.to_numeric(working[value_column], errors="coerce")
        if value_order.notna().any():
            working["_comparison_value_order"] = value_order
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


def _cell_value(row: pd.Series, column: str | None) -> object | None:
    if column is None:
        return None

    value = row.get(column)
    if _is_missing_value(value):
        return None
    return value


def _safe_string(value: object | None) -> str | None:
    if _is_missing_value(value):
        return None

    text = str(value).strip()
    return text or None


def _is_missing_value(value: object | None) -> bool:
    if value is None:
        return True

    try:
        return bool(pd.isna(value))
    except (TypeError, ValueError):
        return False


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
        _render_comparison_summary_panel(table)

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
