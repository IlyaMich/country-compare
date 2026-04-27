from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from country_compare.exports import (
    export_diagnostics_json,
    export_markdown_summary,
    export_table_csv,
    export_tables_csv,
)


@dataclass(frozen=True)
class DemoDiagnostic:
    status: str
    count: int


def test_export_table_csv_writes_dataframe(tmp_path: Path) -> None:
    dataframe = pd.DataFrame(
        [
            {"country_code": "ISR", "value": 1.5},
            {"country_code": "FRA", "value": 2.5},
        ]
    )

    output_path = export_table_csv(dataframe, tmp_path / "table.csv")

    assert output_path.exists()

    loaded = pd.read_csv(output_path)
    pd.testing.assert_frame_equal(loaded, dataframe)


def test_export_tables_csv_writes_multiple_tables(tmp_path: Path) -> None:
    tables = {
        "first.csv": pd.DataFrame([{"value": 1}]),
        "second": pd.DataFrame([{"value": 2}]),
    }

    exported = export_tables_csv(tables, tmp_path)

    assert exported["first.csv"] == tmp_path / "first.csv"
    assert exported["second"] == tmp_path / "second.csv"
    assert (tmp_path / "first.csv").exists()
    assert (tmp_path / "second.csv").exists()


def test_export_diagnostics_json_serializes_dataclasses(tmp_path: Path) -> None:
    output_path = export_diagnostics_json(
        {
            "diagnostic": DemoDiagnostic(status="ok", count=3),
            "path": tmp_path / "artifact.csv",
        },
        tmp_path / "diagnostics.json",
    )

    payload = json.loads(output_path.read_text(encoding="utf-8"))

    assert payload["diagnostic"] == {"count": 3, "status": "ok"}
    assert payload["path"].endswith("artifact.csv")


def test_export_markdown_summary_writes_sections(tmp_path: Path) -> None:
    output_path = export_markdown_summary(
        tmp_path / "summary.md",
        title="Demo Summary",
        sections={
            "Dataset": ["Input rows: 64", "Countries: 4"],
            "Notes": "Synthetic demo data.",
        },
    )

    content = output_path.read_text(encoding="utf-8")

    assert "# Demo Summary" in content
    assert "## Dataset" in content
    assert "- Input rows: 64" in content
    assert "Synthetic demo data." in content
