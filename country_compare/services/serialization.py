from __future__ import annotations

from dataclasses import fields, is_dataclass
from datetime import date, datetime, time
from enum import Enum
import json
import math
from pathlib import Path
from typing import Any, Mapping, Sequence

import pandas as pd

try:  # pragma: no cover - optional dependency in some runtimes
    import numpy as np
except Exception:  # pragma: no cover
    np = None

try:  # pragma: no cover - optional import for serialization only
    from matplotlib.figure import Figure
except Exception:  # pragma: no cover
    Figure = None  # type: ignore[assignment]

DEFAULT_MAX_RECORDS = 500


def serialize_dataframe(
    dataframe: pd.DataFrame,
    *,
    include_records: bool = True,
    max_records: int = DEFAULT_MAX_RECORDS,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "row_count": int(len(dataframe.index)),
        "column_count": int(len(dataframe.columns)),
        "columns": [str(column) for column in dataframe.columns.tolist()],
    }
    if include_records:
        limited = dataframe.head(max_records)
        payload["records"] = to_jsonable(limited.to_dict(orient="records"), max_records=max_records)
        payload["records_truncated"] = bool(len(dataframe.index) > max_records)
    return payload


def serialize_error(error: Any) -> dict[str, Any] | None:
    if error is None:
        return None
    return {
        "code": getattr(error, "code", None),
        "title": getattr(error, "title", None),
        "user_message": getattr(error, "user_message", str(error)),
        "technical_detail": getattr(error, "technical_detail", None),
        "field_errors": to_jsonable(getattr(error, "field_errors", None), dataframe_records=False),
    }


def serialize_comparison_result(
    result: Any,
    *,
    include_records: bool = True,
    max_records: int = DEFAULT_MAX_RECORDS,
) -> dict[str, Any]:
    dataframe = getattr(result, "dataframe", None)
    return {
        "mode": getattr(result, "mode", None),
        "ok": bool(getattr(result, "ok", False)),
        "request": to_jsonable(getattr(result, "request", None), dataframe_records=False, max_records=max_records),
        "dataframe": None
        if not isinstance(dataframe, pd.DataFrame)
        else serialize_dataframe(dataframe, include_records=include_records, max_records=max_records),
        "metadata": to_jsonable(getattr(result, "metadata", {}), dataframe_records=False, max_records=max_records),
        "diagnostics": to_jsonable(getattr(result, "diagnostics", {}), dataframe_records=False, max_records=max_records),
        "warnings": to_jsonable(getattr(result, "warnings", []), dataframe_records=False, max_records=max_records),
        "error": serialize_error(getattr(result, "error", None)),
    }


def serialize_presentation_result(
    presentation: Any,
    *,
    include_records: bool = True,
    max_records: int = DEFAULT_MAX_RECORDS,
) -> dict[str, Any]:
    table = getattr(presentation, "table", None)
    extra_tables = getattr(presentation, "tables", {}) or {}
    extra_charts = getattr(presentation, "charts", {}) or {}

    return {
        "mode": getattr(presentation, "mode", None),
        "ok": bool(getattr(presentation, "ok", False)),
        "request": to_jsonable(
            getattr(presentation, "request", None),
            dataframe_records=False,
            max_records=max_records,
        ),
        "summary": to_jsonable(getattr(presentation, "summary", {}), dataframe_records=False, max_records=max_records),
        "table": None
        if not isinstance(table, pd.DataFrame)
        else serialize_dataframe(table, include_records=include_records, max_records=max_records),
        "tables": {
            str(name): serialize_dataframe(dataframe, include_records=include_records, max_records=max_records)
            for name, dataframe in extra_tables.items()
            if isinstance(dataframe, pd.DataFrame)
        },
        "chart": _serialize_chart(getattr(presentation, "chart", None)),
        "charts": {str(name): _serialize_chart(chart) for name, chart in extra_charts.items()},
        "metadata": to_jsonable(getattr(presentation, "metadata", {}), dataframe_records=False, max_records=max_records),
        "diagnostics": to_jsonable(getattr(presentation, "diagnostics", {}), dataframe_records=False, max_records=max_records),
        "warnings": to_jsonable(getattr(presentation, "warnings", []), dataframe_records=False, max_records=max_records),
        "messages": to_jsonable(getattr(presentation, "messages", []), dataframe_records=False, max_records=max_records),
        "error": serialize_error(getattr(presentation, "error", None)),
    }


def serialize_prediction_service_result(
    result: Any,
    *,
    include_records: bool = True,
    max_records: int = DEFAULT_MAX_RECORDS,
) -> dict[str, Any]:
    dataframe = getattr(result, "dataframe", None)
    prediction_result = getattr(result, "prediction_result", None)
    predicted_comparison_result = getattr(result, "predicted_comparison_result", None)
    backtest_result = getattr(result, "backtest_result", None)

    return {
        "mode": getattr(result, "mode", None),
        "ok": bool(getattr(result, "ok", False)),
        "request": to_jsonable(getattr(result, "request", None), dataframe_records=False, max_records=max_records),
        "dataframe": None
        if not isinstance(dataframe, pd.DataFrame)
        else serialize_dataframe(dataframe, include_records=include_records, max_records=max_records),
        "summary": to_jsonable(getattr(result, "summary", {}), dataframe_records=False, max_records=max_records),
        "metadata": to_jsonable(getattr(result, "metadata", {}), dataframe_records=False, max_records=max_records),
        "diagnostics": to_jsonable(getattr(result, "diagnostics", {}), dataframe_records=False, max_records=max_records),
        "warnings": to_jsonable(getattr(result, "warnings", []), dataframe_records=False, max_records=max_records),
        "prediction_result": to_jsonable(prediction_result, dataframe_records=include_records, max_records=max_records),
        "predicted_comparison_result": to_jsonable(
            predicted_comparison_result,
            dataframe_records=include_records,
            max_records=max_records,
        ),
        "backtest_result": to_jsonable(backtest_result, dataframe_records=include_records, max_records=max_records),
        "error": serialize_error(getattr(result, "error", None)),
    }


def serialize_dataset_summary(summary: Any) -> dict[str, Any]:
    return to_jsonable(summary, dataframe_records=False)


serialize_config_status = serialize_dataset_summary
serialize_overview_status = serialize_dataset_summary
serialize_validation_report = serialize_dataset_summary
serialize_request = serialize_dataset_summary


def dumps_json(payload: Any) -> str:
    return json.dumps(to_jsonable(payload), indent=2, ensure_ascii=False, sort_keys=True)


def to_jsonable(
    value: Any,
    *,
    dataframe_records: bool = True,
    max_records: int = DEFAULT_MAX_RECORDS,
) -> Any:
    if value is None:
        return None

    if isinstance(value, Enum):
        return value.value

    if isinstance(value, (str, int, bool)):
        return value

    if isinstance(value, float):
        return None if math.isnan(value) or math.isinf(value) else value

    if np is not None and isinstance(value, np.generic):
        return to_jsonable(value.item(), dataframe_records=dataframe_records, max_records=max_records)

    if isinstance(value, Path):
        return str(value)

    if isinstance(value, (datetime, date, time)):
        return value.isoformat()

    if isinstance(value, pd.Timestamp):
        return None if pd.isna(value) else value.isoformat()

    if value is pd.NA or value is pd.NaT:
        return None

    if isinstance(value, pd.DataFrame):
        return serialize_dataframe(value, include_records=dataframe_records, max_records=max_records)

    if isinstance(value, pd.Series):
        return to_jsonable(value.to_list(), dataframe_records=dataframe_records, max_records=max_records)

    if Figure is not None and isinstance(value, Figure):
        return _serialize_chart(value)

    if isinstance(value, Mapping):
        return {
            str(key): to_jsonable(item, dataframe_records=dataframe_records, max_records=max_records)
            for key, item in value.items()
        }

    if is_dataclass(value) and not isinstance(value, type):
        return {
            field.name: to_jsonable(
                getattr(value, field.name),
                dataframe_records=dataframe_records,
                max_records=max_records,
            )
            for field in fields(value)
        }

    if hasattr(value, "model_dump"):
        dumped = value.model_dump(mode="json")
        return to_jsonable(dumped, dataframe_records=dataframe_records, max_records=max_records)

    if isinstance(value, Sequence) and not isinstance(value, (bytes, bytearray)):
        return [
            to_jsonable(item, dataframe_records=dataframe_records, max_records=max_records)
            for item in value
        ]

    public_dict = getattr(value, "__dict__", None)
    if isinstance(public_dict, dict):
        return {
            str(key): to_jsonable(item, dataframe_records=dataframe_records, max_records=max_records)
            for key, item in public_dict.items()
            if not str(key).startswith("_")
        }

    try:
        if pd.isna(value):
            return None
    except Exception:
        pass

    return str(value)


def _serialize_chart(chart: Any) -> dict[str, Any] | None:
    if chart is None:
        return None
    return {
        "type": chart.__class__.__name__,
        "present": True,
    }
