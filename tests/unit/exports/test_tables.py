from __future__ import annotations

import pandas as pd

from country_compare.exports.tables import export_table_csv, export_tables_csv


def test_export_table_csv_creates_parent_dirs_and_round_trips(tmp_path) -> None:
    dataframe = pd.DataFrame(
        [
            {"country_code": "ISR", "metric_id": "gdp_per_capita", "value": 59000.0},
            {"country_code": "DEU", "metric_id": "gdp_per_capita", "value": 69500.0},
        ]
    )

    output_path = tmp_path / "nested" / "exports" / "single_metric.csv"

    result_path = export_table_csv(dataframe, output_path)

    assert result_path == output_path
    assert output_path.exists()

    round_tripped = pd.read_csv(output_path)

    assert list(round_tripped.columns) == ["country_code", "metric_id", "value"]
    assert round_tripped.to_dict("records") == [
        {"country_code": "ISR", "metric_id": "gdp_per_capita", "value": 59000.0},
        {"country_code": "DEU", "metric_id": "gdp_per_capita", "value": 69500.0},
    ]


def test_export_table_csv_can_include_index(tmp_path) -> None:
    dataframe = pd.DataFrame(
        [{"country_code": "ISR", "value": 1.0}],
        index=pd.Index(["row-1"], name="row_id"),
    )

    output_path = tmp_path / "with_index.csv"

    export_table_csv(dataframe, output_path, index=True)

    round_tripped = pd.read_csv(output_path)

    assert list(round_tripped.columns) == ["row_id", "country_code", "value"]
    assert round_tripped.loc[0, "row_id"] == "row-1"


def test_export_tables_csv_exports_multiple_tables_and_adds_csv_suffix(
    tmp_path,
) -> None:
    tables = {
        "comparison": pd.DataFrame([{"country_code": "ISR", "rank": 1}]),
        "diagnostics.csv": pd.DataFrame([{"check": "coverage", "status": "ok"}]),
    }

    exported = export_tables_csv(tables, tmp_path)

    assert set(exported) == {"comparison", "diagnostics.csv"}
    assert exported["comparison"] == tmp_path / "comparison.csv"
    assert exported["diagnostics.csv"] == tmp_path / "diagnostics.csv"

    assert (tmp_path / "comparison.csv").exists()
    assert (tmp_path / "diagnostics.csv").exists()

    comparison = pd.read_csv(tmp_path / "comparison.csv")
    diagnostics = pd.read_csv(tmp_path / "diagnostics.csv")

    assert comparison.to_dict("records") == [{"country_code": "ISR", "rank": 1}]
    assert diagnostics.to_dict("records") == [{"check": "coverage", "status": "ok"}]
