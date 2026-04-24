from __future__ import annotations

from dataclasses import dataclass

import pandas as pd
from matplotlib.figure import Figure

from country_compare.services.results import AppMessage, ComparisonResult, PresentationResult, PredictionServiceResult
from country_compare.services.serialization import (
    serialize_comparison_result,
    serialize_error,
    serialize_presentation_result,
    serialize_prediction_service_result,
)


@dataclass
class StubError:
    code: str = "selection_invalid"
    title: str = "Selection is invalid"
    user_message: str = "Bad input"
    technical_detail: str = "trace"
    field_errors: dict[str, str] | None = None


@dataclass
class StubRequest:
    mode: str = "single_metric"
    countries: list[str] | None = None


class _Error:
    code = "missing_country"
    title = "Missing country"
    user_message = "Country not found"
    technical_detail = "USA"
    field_errors = {"country_code": "USA"}


def test_serialize_error_returns_json_safe_payload() -> None:
    payload = serialize_error(StubError(field_errors={"metric_id": "Missing"}))

    assert payload == {
        "code": "selection_invalid",
        "title": "Selection is invalid",
        "user_message": "Bad input",
        "technical_detail": "trace",
        "field_errors": {"metric_id": "Missing"},
    }


def test_serialize_comparison_result_includes_dataframe_summary_and_records() -> None:
    result = ComparisonResult(
        mode="single_metric",
        request=StubRequest(countries=["ISR", "DEU"]),
        dataframe=pd.DataFrame(
            [
                {"country_code": "ISR", "value": 1.2, "missing": pd.NA},
                {"country_code": "DEU", "value": 2.4, "missing": pd.NA},
            ]
        ),
        metadata={"metric_id": "gdp_per_capita"},
        diagnostics={"ranked": True},
    )

    payload = serialize_comparison_result(result)

    assert payload["ok"] is True
    assert payload["dataframe"]["row_count"] == 2
    assert payload["dataframe"]["columns"] == ["country_code", "value", "missing"]
    assert payload["dataframe"]["records"][0]["missing"] is None
    assert payload["metadata"]["metric_id"] == "gdp_per_capita"
    assert payload["diagnostics"]["ranked"] is True


def test_serialize_presentation_result_marks_chart_presence() -> None:
    figure = Figure()
    presentation = PresentationResult(
        mode="weighted_score",
        request=StubRequest(mode="weighted_score", countries=["ISR", "DEU"]),
        summary={"title": "Weighted"},
        table=pd.DataFrame([{"country_code": "DEU", "weighted_score": 0.95}]),
        chart=figure,
        metadata={"Selection": {"Profile": "default"}},
        diagnostics={"scored": True},
        messages=[AppMessage(level="success", text="Done")],
    )

    payload = serialize_presentation_result(presentation)

    assert payload["ok"] is True
    assert payload["chart"]["present"] is True
    assert payload["table"]["row_count"] == 1
    assert payload["messages"][0]["text"] == "Done"


def test_serialize_prediction_service_result_includes_summary_and_error() -> None:
    result = PredictionServiceResult(
        mode="single_forecast",
        request={"country_code": "USA", "metric_id": "gdp_per_capita"},
        dataframe=pd.DataFrame([{"country_code": "ISR", "value": 30.0}]),
        summary={"forecast": {"row_count": 1}},
        error=_Error(),
    )

    payload = serialize_prediction_service_result(result)

    assert payload["mode"] == "single_forecast"
    assert payload["summary"]["forecast"]["row_count"] == 1
    assert payload["dataframe"]["row_count"] == 1
    assert payload["error"]["code"] == "missing_country"