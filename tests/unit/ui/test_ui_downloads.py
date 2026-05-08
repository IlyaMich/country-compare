from __future__ import annotations

import json
from dataclasses import dataclass
from enum import StrEnum

import pandas as pd

from country_compare.ui.components.downloads import (
    build_result_markdown_summary,
    dataframe_to_csv_bytes,
    markdown_to_bytes,
    payload_to_json_bytes,
)


class DemoStatus(StrEnum):
    OK = "ok"


@dataclass(frozen=True)
class DemoDiagnostic:
    status: DemoStatus
    count: int


def test_dataframe_to_csv_bytes_omits_index() -> None:
    dataframe = pd.DataFrame(
        [
            {"country_code": "ISR", "value": 1.5},
            {"country_code": "FRA", "value": 2.5},
        ]
    )

    payload = dataframe_to_csv_bytes(dataframe)

    assert payload.decode("utf-8").splitlines() == [
        "country_code,value",
        "ISR,1.5",
        "FRA,2.5",
    ]


def test_payload_to_json_bytes_serializes_dataclass_and_enum() -> None:
    payload = payload_to_json_bytes(
        {
            "diagnostic": DemoDiagnostic(status=DemoStatus.OK, count=2),
            "items": {"a", "b"},
        }
    )

    decoded = json.loads(payload.decode("utf-8"))

    assert decoded["diagnostic"] == {"count": 2, "status": "ok"}
    assert sorted(decoded["items"]) == ["a", "b"]


def test_build_result_markdown_summary() -> None:
    markdown = build_result_markdown_summary(
        title="Result Summary",
        sections={
            "Dataset": ["Rows: 64", "Countries: 4"],
            "Notes": "Synthetic demo result.",
        },
    )

    assert "# Result Summary" in markdown
    assert "## Dataset" in markdown
    assert "- Rows: 64" in markdown
    assert "Synthetic demo result." in markdown


def test_markdown_to_bytes() -> None:
    assert markdown_to_bytes("# Demo\n") == b"# Demo\n"
