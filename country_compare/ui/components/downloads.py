from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import asdict, is_dataclass
from enum import Enum
from typing import Any

import pandas as pd
import streamlit as st


def dataframe_to_csv_bytes(dataframe: pd.DataFrame) -> bytes:
    """Return a dataframe as UTF-8 CSV bytes without the pandas index."""
    return dataframe.to_csv(index=False).encode("utf-8")


def payload_to_json_bytes(payload: Any) -> bytes:
    """Return JSON-serializable payload bytes."""
    return json.dumps(
        _to_jsonable(payload),
        indent=2,
        sort_keys=True,
    ).encode("utf-8")


def markdown_to_bytes(markdown: str) -> bytes:
    """Return Markdown content as UTF-8 bytes."""
    return markdown.encode("utf-8")


def build_result_markdown_summary(
    *,
    title: str,
    sections: Mapping[str, str | list[str]],
) -> str:
    lines: list[str] = [f"# {title}", ""]

    for heading, content in sections.items():
        lines.extend([f"## {heading}", ""])

        if isinstance(content, str):
            lines.extend([content, ""])
            continue

        for item in content:
            lines.append(f"- {item}")
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def render_dataframe_download_button(
    dataframe: pd.DataFrame,
    *,
    label: str,
    file_name: str,
    key: str,
) -> None:
    """Render a Streamlit CSV download button for a dataframe."""
    st.download_button(
        label=label,
        data=dataframe_to_csv_bytes(dataframe),
        file_name=_ensure_suffix(file_name, ".csv"),
        mime="text/csv",
        key=key,
    )


def render_json_download_button(
    payload: Any,
    *,
    label: str,
    file_name: str,
    key: str,
) -> None:
    """Render a Streamlit JSON download button."""
    st.download_button(
        label=label,
        data=payload_to_json_bytes(payload),
        file_name=_ensure_suffix(file_name, ".json"),
        mime="application/json",
        key=key,
    )


def render_markdown_download_button(
    markdown: str,
    *,
    label: str,
    file_name: str,
    key: str,
) -> None:
    """Render a Streamlit Markdown download button."""
    st.download_button(
        label=label,
        data=markdown_to_bytes(markdown),
        file_name=_ensure_suffix(file_name, ".md"),
        mime="text/markdown",
        key=key,
    )


def render_result_downloads(
    *,
    table: pd.DataFrame | None = None,
    diagnostics: Any | None = None,
    summary_markdown: str | None = None,
    base_file_name: str = "country_compare_result",
    key_prefix: str = "download",
) -> None:
    """Render standard result download buttons for table, diagnostics, and summary."""
    if table is None and diagnostics is None and summary_markdown is None:
        st.caption("No downloadable result is available yet.")
        return

    st.subheader("Export results")

    if table is not None:
        render_dataframe_download_button(
            table,
            label="Download table CSV",
            file_name=f"{base_file_name}.csv",
            key=f"{key_prefix}_table_csv",
        )

    if diagnostics is not None:
        render_json_download_button(
            diagnostics,
            label="Download diagnostics JSON",
            file_name=f"{base_file_name}_diagnostics.json",
            key=f"{key_prefix}_diagnostics_json",
        )

    if summary_markdown is not None:
        render_markdown_download_button(
            summary_markdown,
            label="Download summary Markdown",
            file_name=f"{base_file_name}_summary.md",
            key=f"{key_prefix}_summary_md",
        )


def _ensure_suffix(file_name: str, suffix: str) -> str:
    return file_name if file_name.endswith(suffix) else f"{file_name}{suffix}"


def _to_jsonable(value: Any) -> Any:
    if is_dataclass(value):
        return _to_jsonable(asdict(value))

    if isinstance(value, Enum):
        return value.value

    if isinstance(value, dict):
        return {str(key): _to_jsonable(item) for key, item in value.items()}

    if isinstance(value, list | tuple | set):
        return [_to_jsonable(item) for item in value]

    if hasattr(value, "model_dump"):
        return _to_jsonable(value.model_dump(mode="json"))

    if hasattr(value, "to_dict"):
        return _to_jsonable(value.to_dict())

    return value
