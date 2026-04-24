from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd


def build_source_defaults(source_spec: Any | None) -> dict[str, Any]:
    if source_spec is None:
        return {}
    return {
        "source_name": getattr(source_spec, "source_name", None),
        "source_url": getattr(source_spec, "source_url", None),
        "dataset_version": getattr(source_spec, "dataset_version", None),
        "metric_id": getattr(source_spec, "metric_id", None),
        "metric_name": getattr(source_spec, "metric_name", None),
        "unit": getattr(source_spec, "unit", None),
        "category": getattr(source_spec, "category", None),
        "higher_is_better": getattr(source_spec, "higher_is_better", None),
    }


def stamp_metadata_defaults(dataframe: pd.DataFrame, *, source_spec: Any | None) -> pd.DataFrame:
    result = dataframe.copy(deep=True)
    defaults = build_source_defaults(source_spec)
    asset_path = None
    if source_spec is not None:
        asset_path = getattr(getattr(source_spec, "metadata", {}), "get", lambda *_: None)("path")
        if asset_path is None and getattr(source_spec, "path", None) is not None:
            asset_path = str(getattr(source_spec, "path"))
    notes_default = None
    if asset_path is not None:
        notes_default = f"ingested_from={Path(str(asset_path)).name}"
    if "notes" not in result.columns:
        result["notes"] = notes_default
    elif notes_default is not None:
        result["notes"] = result["notes"].fillna(notes_default)
    for column, default_value in defaults.items():
        if default_value is None:
            continue
        if column not in result.columns:
            result[column] = default_value
            continue
        series = result[column]
        if pd.api.types.is_string_dtype(series.dtype) or series.dtype == object:
            result[column] = series.replace("", pd.NA).fillna(default_value)
        else:
            result[column] = series.fillna(default_value)
    return result
