from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import pandas as pd

from country_compare.api.schemas.common import ErrorDetail, ResultEnvelope, TablePayload
from country_compare.services import serialization as service_serialization
from country_compare.services.errors import AppError

DEFAULT_MAX_RECORDS = service_serialization.DEFAULT_MAX_RECORDS


def _normalize_pandas_missing(value: Any) -> Any:
    if value is pd.NaT or value is pd.NA:
        return None

    if isinstance(value, dict):
        return {key: _normalize_pandas_missing(item) for key, item in value.items()}

    if isinstance(value, list):
        return [_normalize_pandas_missing(item) for item in value]

    if isinstance(value, tuple):
        return tuple(_normalize_pandas_missing(item) for item in value)

    return value


def to_jsonable(
    value: Any,
    *,
    dataframe_records: bool = True,
    max_records: int = DEFAULT_MAX_RECORDS,
) -> Any:
    """Convert a value into a JSON-safe structure for API responses.

    The services layer already owns the canonical conversion rules for pandas,
    NumPy, dataclasses, Pydantic models, paths, dates, and nested containers.
    The API layer intentionally wraps that implementation instead of
    duplicating it.
    """

    return service_serialization.to_jsonable(
        _normalize_pandas_missing(value),
        dataframe_records=dataframe_records,
        max_records=max_records,
    )


def serialize_dataframe(
    dataframe: pd.DataFrame,
    *,
    include_records: bool = True,
    max_records: int = DEFAULT_MAX_RECORDS,
) -> TablePayload:
    """Serialize a DataFrame into the API table payload shape."""

    payload = service_serialization.serialize_dataframe(
        dataframe,
        include_records=include_records,
        max_records=max_records,
    )
    return TablePayload.model_validate(payload)


def serialize_error(error: Any) -> ErrorDetail | None:
    """Serialize an app/domain error into the public API error shape."""

    if error is None:
        return None

    if isinstance(error, ErrorDetail):
        return error

    if isinstance(error, AppError):
        return ErrorDetail.from_app_error(error)

    serialized = service_serialization.serialize_error(error)
    if serialized is not None:
        return _error_detail_from_mapping(serialized)

    return ErrorDetail(
        code="error",
        message=str(error),
        details={},
    )


def serialize_result_envelope(
    result: Any,
    *,
    mode: str | None = None,
    include_records: bool = True,
    max_records: int = DEFAULT_MAX_RECORDS,
) -> ResultEnvelope:
    """Serialize a service result into the common API result envelope."""

    payload = _serialize_result_payload(
        result,
        include_records=include_records,
        max_records=max_records,
    )
    normalized = _normalize_result_payload(payload, mode=mode)
    return ResultEnvelope.model_validate(normalized)


def _serialize_result_payload(
    result: Any,
    *,
    include_records: bool,
    max_records: int,
) -> dict[str, Any]:
    if isinstance(result, Mapping):
        jsonable_result = to_jsonable(
            result,
            dataframe_records=include_records,
            max_records=max_records,
        )
        if isinstance(jsonable_result, Mapping):
            return dict(jsonable_result)

    if hasattr(result, "prediction_result") or hasattr(result, "backtest_result"):
        return service_serialization.serialize_prediction_service_result(
            result,
            include_records=include_records,
            max_records=max_records,
        )

    if (
        hasattr(result, "table")
        or hasattr(result, "tables")
        or hasattr(result, "messages")
    ):
        return service_serialization.serialize_presentation_result(
            result,
            include_records=include_records,
            max_records=max_records,
        )

    if hasattr(result, "dataframe"):
        return service_serialization.serialize_comparison_result(
            result,
            include_records=include_records,
            max_records=max_records,
        )

    jsonable_value = to_jsonable(
        result,
        dataframe_records=include_records,
        max_records=max_records,
    )
    if isinstance(jsonable_value, Mapping):
        return dict(jsonable_value)

    return {
        "ok": result is not None,
        "summary": {"value": jsonable_value},
    }


def _normalize_result_payload(
    payload: Mapping[str, Any],
    *,
    mode: str | None,
) -> dict[str, Any]:
    tables = _extract_tables(payload)
    charts = _extract_charts(payload)
    error = serialize_error(payload.get("error"))

    return {
        "ok": bool(payload.get("ok", error is None)),
        "mode": mode if mode is not None else _optional_string(payload.get("mode")),
        "request": _as_dict(payload.get("request")),
        "summary": _as_dict(payload.get("summary")),
        "metadata": _as_dict(payload.get("metadata")),
        "diagnostics": _as_dict(payload.get("diagnostics")),
        "warnings": _as_string_list(payload.get("warnings")),
        "messages": _as_list(payload.get("messages")),
        "tables": tables,
        "charts": charts,
        "error": error,
    }


def _extract_tables(payload: Mapping[str, Any]) -> dict[str, TablePayload]:
    tables: dict[str, TablePayload] = {}

    main_table = payload.get("table")
    if main_table is None:
        main_table = payload.get("dataframe")

    if main_table is not None:
        tables["main"] = TablePayload.model_validate(main_table)

    extra_tables = payload.get("tables")
    if isinstance(extra_tables, Mapping):
        for name, table_payload in extra_tables.items():
            tables[str(name)] = TablePayload.model_validate(table_payload)

    return tables


def _extract_charts(payload: Mapping[str, Any]) -> dict[str, Any]:
    charts: dict[str, Any] = {}

    chart = payload.get("chart")
    if chart is not None:
        charts["main"] = to_jsonable(chart, dataframe_records=False)

    extra_charts = payload.get("charts")
    if isinstance(extra_charts, Mapping):
        for name, chart_payload in extra_charts.items():
            charts[str(name)] = to_jsonable(chart_payload, dataframe_records=False)

    return charts


def _error_detail_from_mapping(error: Mapping[str, Any]) -> ErrorDetail:
    details: dict[str, Any] = {}

    for key in ("title", "technical_detail", "field_errors"):
        value = error.get(key)
        if value:
            details[key] = to_jsonable(value, dataframe_records=False)

    raw_details = error.get("details")
    if isinstance(raw_details, Mapping):
        details.update(to_jsonable(raw_details, dataframe_records=False))

    return ErrorDetail(
        code=str(error.get("code") or "error"),
        message=str(
            error.get("message")
            or error.get("user_message")
            or error.get("title")
            or "An error occurred."
        ),
        details=details,
    )


def _optional_string(value: Any) -> str | None:
    if value is None:
        return None
    return str(value)


def _as_dict(value: Any) -> dict[str, Any]:
    jsonable_value = to_jsonable(value, dataframe_records=False)
    if jsonable_value is None:
        return {}
    if isinstance(jsonable_value, Mapping):
        return {str(key): item for key, item in jsonable_value.items()}
    return {"value": jsonable_value}


def _as_list(value: Any) -> list[Any]:
    jsonable_value = to_jsonable(value, dataframe_records=False)
    if jsonable_value is None:
        return []
    if isinstance(jsonable_value, list):
        return jsonable_value
    return [jsonable_value]


def _as_string_list(value: Any) -> list[str]:
    return [str(item) for item in _as_list(value)]
