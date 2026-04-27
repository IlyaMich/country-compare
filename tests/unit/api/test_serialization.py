from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from country_compare.api.schemas.common import ErrorDetail, ResultEnvelope, TablePayload
from country_compare.api.serialization import (
    serialize_dataframe,
    serialize_error,
    serialize_result_envelope,
    to_jsonable,
)
from country_compare.services.errors import AppError
from country_compare.services.results import ComparisonResult, PresentationResult


@dataclass(frozen=True)
class DummyRequest:
    countries: tuple[str, ...]
    year: int


def test_to_jsonable_converts_common_non_json_values() -> None:
    payload = {
        "pd_na": pd.NA,
        "nan": float("nan"),
        "nat": pd.NaT,
        "numpy_int": np.int64(2024),
        "numpy_float": np.float64(12.5),
        "path": Path("data/processed/metrics.parquet"),
        "date": date(2024, 1, 2),
        "datetime": datetime(2024, 1, 2, 3, 4, 5),
        "time": time(3, 4, 5),
    }

    serialized = to_jsonable(payload)

    assert serialized["pd_na"] is None
    assert serialized["nan"] is None
    assert serialized["nat"] is None
    assert serialized["numpy_int"] == 2024
    assert isinstance(serialized["numpy_int"], int)
    assert serialized["numpy_float"] == 12.5
    assert isinstance(serialized["numpy_float"], float)
    assert serialized["path"] == "data/processed/metrics.parquet"
    assert serialized["date"] == "2024-01-02"
    assert serialized["datetime"] == "2024-01-02T03:04:05"
    assert serialized["time"] == "03:04:05"


def test_serialize_dataframe_preserves_shape_columns_and_truncates_records() -> None:
    dataframe = pd.DataFrame(
        {
            "country_code": ["ISR", "FRA", "USA"],
            "year": np.array([2022, 2023, 2024], dtype=np.int64),
            "value": [10.0, pd.NA, np.float64(30.5)],
        }
    )

    payload = serialize_dataframe(dataframe, max_records=2)

    assert isinstance(payload, TablePayload)
    assert payload.row_count == 3
    assert payload.column_count == 3
    assert payload.columns == ["country_code", "year", "value"]
    assert payload.records_truncated is True
    assert payload.records == [
        {"country_code": "ISR", "year": 2022, "value": 10.0},
        {"country_code": "FRA", "year": 2023, "value": None},
    ]


def test_serialize_dataframe_can_omit_records() -> None:
    dataframe = pd.DataFrame({"year": [2023, 2024], "value": [1, 2]})

    payload = serialize_dataframe(dataframe, include_records=False)

    assert payload.row_count == 2
    assert payload.column_count == 2
    assert payload.columns == ["year", "value"]
    assert payload.records == []
    assert payload.records_truncated is False


def test_serialize_error_maps_app_error_to_public_error_detail() -> None:
    error = AppError(
        code="invalid_metric",
        title="Invalid metric",
        user_message="Unknown metric_id: bad_metric",
        technical_detail="metric was not found in metrics.yaml",
        field_errors={"metric_id": "bad_metric"},
    )

    payload = serialize_error(error)

    assert isinstance(payload, ErrorDetail)
    assert payload.model_dump() == {
        "code": "invalid_metric",
        "message": "Unknown metric_id: bad_metric",
        "details": {
            "title": "Invalid metric",
            "technical_detail": "metric was not found in metrics.yaml",
            "field_errors": {"metric_id": "bad_metric"},
        },
    }


def test_serialize_result_envelope_normalizes_comparison_dataframe() -> None:
    dataframe = pd.DataFrame(
        {
            "country_code": ["ISR", "FRA"],
            "year": [2024, 2024],
            "value": [100.0, 200.0],
        }
    )
    result = ComparisonResult(
        mode="single_metric",
        request=DummyRequest(countries=("ISR", "FRA"), year=2024),
        dataframe=dataframe,
        metadata={"row_count": np.int64(2)},
        diagnostics={"used_latest_year": False},
        warnings=["example warning"],
    )

    envelope = serialize_result_envelope(result)

    assert isinstance(envelope, ResultEnvelope)
    assert envelope.ok is True
    assert envelope.mode == "single_metric"
    assert envelope.request == {"countries": ["ISR", "FRA"], "year": 2024}
    assert envelope.metadata == {"row_count": 2}
    assert envelope.diagnostics == {"used_latest_year": False}
    assert envelope.warnings == ["example warning"]
    assert envelope.tables["main"].columns == ["country_code", "year", "value"]
    assert envelope.tables["main"].records[0] == {
        "country_code": "ISR",
        "year": 2024,
        "value": 100.0,
    }


def test_serialize_result_envelope_normalizes_presentation_tables_and_charts() -> None:
    main_table = pd.DataFrame({"country_code": ["ISR"], "score": [0.9]})
    extra_table = pd.DataFrame({"metric_id": ["gdp_per_capita"], "weight": [1.0]})
    result = PresentationResult(
        mode="profile_score",
        request={"profile_name": "economic_outlook"},
        summary={"title": "Profile score"},
        table=main_table,
        tables={"weights": extra_table},
        charts={"summary": {"type": "bar", "present": True}},
        messages=[{"level": "info", "text": "done"}],
    )

    envelope = serialize_result_envelope(result, max_records=10)

    assert envelope.ok is True
    assert envelope.mode == "profile_score"
    assert envelope.summary == {"title": "Profile score"}
    assert set(envelope.tables) == {"main", "weights"}
    assert envelope.tables["main"].records == [{"country_code": "ISR", "score": 0.9}]
    assert envelope.tables["weights"].records == [
        {"metric_id": "gdp_per_capita", "weight": 1.0}
    ]
    assert envelope.charts == {"summary": {"type": "dict", "present": True}}
    assert envelope.messages == [{"level": "info", "text": "done"}]


def test_serialize_result_envelope_accepts_mapping_payload() -> None:
    envelope = serialize_result_envelope(
        {
            "ok": True,
            "mode": "custom",
            "request": {"country_codes": ["ISR"]},
            "tables": {
                "main": {
                    "row_count": 1,
                    "column_count": 1,
                    "columns": ["country_code"],
                    "records": [{"country_code": "ISR"}],
                    "records_truncated": False,
                }
            },
        }
    )

    assert envelope.ok is True
    assert envelope.mode == "custom"
    assert envelope.tables["main"].records == [{"country_code": "ISR"}]


def assert_json_safe(value: Any) -> None:
    if value is None or isinstance(value, (str, int, float, bool)):
        return
    if isinstance(value, list):
        for item in value:
            assert_json_safe(item)
        return
    if isinstance(value, dict):
        for key, item in value.items():
            assert isinstance(key, str)
            assert_json_safe(item)
        return

    raise AssertionError(f"Non-JSON-safe value leaked: {type(value)!r}")


def test_result_envelope_model_dump_is_json_safe() -> None:
    dataframe = pd.DataFrame(
        {"year": np.array([2024], dtype=np.int64), "value": [pd.NA]}
    )
    envelope = serialize_result_envelope(
        ComparisonResult(
            mode="single_metric",
            request={"year": np.int64(2024)},
            dataframe=dataframe,
        )
    )

    assert_json_safe(envelope.model_dump())
