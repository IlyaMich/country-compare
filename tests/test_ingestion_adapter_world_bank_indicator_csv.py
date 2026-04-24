from __future__ import annotations

from pathlib import Path

import pandas as pd

from country_compare.pipelines.engine import PipelineEngine
from country_compare.pipelines.models import ProcessingRequest, SourceSpec
from country_compare.data.ingestion.registry import has_source_adapter


def _write_world_bank_csv(path: Path, dataframe: pd.DataFrame) -> None:
    preamble = "\n".join(
        [
            "Data Source,World Bank Data",
            "",
            "Last Updated Date,2026-01-01",
            "",
        ]
    )
    path.write_text(preamble + "\n", encoding="utf-8")
    dataframe.to_csv(path, mode="a", index=False)


def test_world_bank_indicator_csv_is_registered() -> None:
    assert has_source_adapter("world_bank_indicator_csv") is True


def test_world_bank_indicator_csv_filters_aggregate_rows_before_melt(tmp_path: Path) -> None:
    raw = pd.DataFrame(
        {
            "Country Name": ["World", "Israel"],
            "Country Code": ["WLD", "ISR"],
            "Indicator Name": ["GDP, current US$", "GDP, current US$"],
            "Indicator Code": ["NY.GDP.MKTP.CD", "NY.GDP.MKTP.CD"],
            "2022": [100.0, 200.0],
            "2023": [110.0, 210.0],
        }
    )
    csv_path = tmp_path / "wb_gdp_current_usd.csv"
    _write_world_bank_csv(csv_path, raw)

    request = ProcessingRequest(
        sources=[
            SourceSpec(
                source_id="wb_gdp_current_usd",
                adapter_id="world_bank_indicator_csv",
                path=csv_path.name,
                metric_id="gdp_current_usd",
                metric_name="GDP Current USD",
                unit="TODO_UNIT",
                category="TODO_CATEGORY",
                higher_is_better=True,
                source_name="World Bank",
                source_url="https://data.worldbank.org/",
                expected_indicator_code="NY.GDP.MKTP.CD",
                filter_to_allowed_country_codes=True,
            )
        ],
        raw_root=tmp_path,
    )

    result = PipelineEngine().run(request)

    assert result.ok is True
    assert result.canonical_dataframe is not None
    assert set(result.canonical_dataframe["country_code"].tolist()) == {"ISR"}
    assert len(result.canonical_dataframe.index) == 2
    source_result = result.source_results[0]
    assert any(issue.code == "unsupported_country_code_dropped" for issue in source_result.issues)
    assert source_result.rejected_row_count == 1


def test_world_bank_indicator_csv_fails_on_indicator_code_mismatch(tmp_path: Path) -> None:
    raw = pd.DataFrame(
        {
            "Country Name": ["Israel"],
            "Country Code": ["ISR"],
            "Indicator Name": ["GDP, current US$"],
            "Indicator Code": ["NY.GDP.MKTP.CD"],
            "2023": [210.0],
        }
    )
    csv_path = tmp_path / "wb_gdp_current_usd.csv"
    _write_world_bank_csv(csv_path, raw)

    request = ProcessingRequest(
        sources=[
            SourceSpec(
                source_id="wb_gdp_current_usd",
                adapter_id="world_bank_indicator_csv",
                path=csv_path.name,
                metric_id="gdp_current_usd",
                metric_name="GDP Current USD",
                unit="TODO_UNIT",
                category="TODO_CATEGORY",
                higher_is_better=True,
                source_name="World Bank",
                source_url="https://data.worldbank.org/",
                expected_indicator_code="WRONG.CODE",
                filter_to_allowed_country_codes=True,
            )
        ],
        raw_root=tmp_path,
    )

    result = PipelineEngine().run(request)

    assert result.ok is False
    assert result.canonical_dataframe is None
    assert result.source_results[0].ok is False
    assert "indicator_code mismatch" in (result.source_results[0].error or "")
