from __future__ import annotations

import re
from typing import Any

import pandas as pd
import streamlit as st


def render_presentation_exports(
    presentation: Any,
    *,
    presentation_service: Any,
    debug: bool = False,
    key_prefix: str = "compare_export",
) -> None:
    if presentation is None or getattr(presentation, "error", None) is not None:
        return

    table = getattr(presentation, "table", None)
    extra_tables = getattr(presentation, "tables", {}) or {}
    chart = getattr(presentation, "chart", None)
    diagnostics = getattr(presentation, "diagnostics", {}) or {}
    metadata = getattr(presentation, "metadata", {}) or {}

    has_exports = (
        isinstance(table, pd.DataFrame)
        or bool(extra_tables)
        or chart is not None
        or metadata
        or diagnostics
    )
    if not has_exports:
        return

    with st.expander("Export & diagnostics", expanded=False):
        if isinstance(table, pd.DataFrame):
            st.download_button(
                "Download main table CSV",
                data=presentation_service.export_table_csv_bytes(table),
                file_name=f"{_slugify(getattr(presentation, 'mode', 'comparison'))}_table.csv",
                mime="text/csv",
                key=f"{key_prefix}_table_csv",
            )

        for index, (title, dataframe) in enumerate(extra_tables.items()):
            if isinstance(dataframe, pd.DataFrame):
                st.download_button(
                    f"Download {title} CSV",
                    data=presentation_service.export_table_csv_bytes(dataframe),
                    file_name=f"{_slugify(title)}.csv",
                    mime="text/csv",
                    key=f"{key_prefix}_table_extra_{index}",
                )

        if chart is not None:
            st.download_button(
                "Download chart PNG",
                data=presentation_service.export_chart_png_bytes(chart),
                file_name=f"{_slugify(getattr(presentation, 'mode', 'comparison'))}_chart.png",
                mime="image/png",
                key=f"{key_prefix}_chart_png",
            )

        st.download_button(
            "Download presentation bundle JSON",
            data=presentation_service.export_presentation_bundle_json_bytes(
                presentation
            ),
            file_name=f"{_slugify(getattr(presentation, 'mode', 'comparison'))}_bundle.json",
            mime="application/json",
            key=f"{key_prefix}_bundle_json",
        )

        if metadata:
            st.download_button(
                "Download metadata JSON",
                data=presentation_service.export_metadata_json_bytes(metadata),
                file_name=f"{_slugify(getattr(presentation, 'mode', 'comparison'))}_metadata.json",
                mime="application/json",
                key=f"{key_prefix}_metadata_json",
            )

        if diagnostics and debug:
            st.download_button(
                "Download diagnostics JSON",
                data=presentation_service.export_diagnostics_json_bytes(diagnostics),
                file_name=(
                    f"{_slugify(getattr(presentation, 'mode', 'comparison'))}_diagnostics.json"
                ),
                mime="application/json",
                key=f"{key_prefix}_diagnostics_json",
            )


def _slugify(text: str) -> str:
    normalized = re.sub(r"[^a-zA-Z0-9]+", "_", str(text).strip().lower())
    return normalized.strip("_") or "export"
