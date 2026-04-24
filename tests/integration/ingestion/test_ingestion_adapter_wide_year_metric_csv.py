from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from country_compare.data.ingestion.adapters.wide_year_metric_csv import (
    WideYearMetricCsvAdapter,
)
from country_compare.pipelines.acquisition.directory import DirectoryRawAcquirer
from country_compare.pipelines.models import SourceSpec


def _make_source(path: str) -> SourceSpec:
    return SourceSpec(
        source_id="wide_metric",
        adapter_id="wide_year_metric_csv",
        path=path,
        metric_id="gdp_per_capita",
        metric_name="GDP per capita",
        unit="USD",
        category="economy",
        higher_is_better=True,
        source_name="Example Source",
        source_url="https://example.org/gdp",
    )


def test_adapter_transforms_wide_csv_to_canonical(tmp_path: Path) -> None:
    raw = pd.DataFrame(
        {
            "Country Name": ["Israel", "Germany"],
            "Country Code": ["ISR", "DEU"],
            "2022": [52000, 61000],
            "2023": [54000, 65000],
        }
    )
    path = tmp_path / "wide.csv"
    raw.to_csv(path, index=False)

    asset = DirectoryRawAcquirer().acquire(_make_source(path.name), raw_root=tmp_path)[
        0
    ]
    result = WideYearMetricCsvAdapter().process(
        [asset], source_spec=_make_source(path.name)
    )

    assert len(result.dataframe.index) == 4
    assert list(result.dataframe.columns[:5]) == [
        "country_code",
        "country_name",
        "metric_id",
        "metric_name",
        "value",
    ]
    assert result.dataframe["metric_id"].nunique() == 1
    assert result.issues == []


def test_adapter_drops_bad_rows_and_captures_issues(tmp_path: Path) -> None:
    raw = pd.DataFrame(
        {
            "Country Name": ["Israel", "Germany", "Unknownland", None],
            "Country Code": ["ISR", "DEU", "", None],
            "2022": [52000, "not-a-number", 1000, None],
            "2023": [54000, 65000, None, None],
        }
    )
    path = tmp_path / "wide_bad.csv"
    raw.to_csv(path, index=False)

    source = _make_source(path.name)
    asset = DirectoryRawAcquirer().acquire(source, raw_root=tmp_path)[0]
    result = WideYearMetricCsvAdapter().process([asset], source_spec=source)

    assert len(result.dataframe.index) == 3
    issue_codes = {issue.code for issue in result.issues}
    assert "missing_country_code_dropped" in issue_codes
    assert "non_numeric_value_dropped" in issue_codes
    assert "blank_country_row_dropped" in issue_codes


def test_adapter_fails_when_required_country_columns_are_missing(
    tmp_path: Path,
) -> None:
    raw = pd.DataFrame({"Country Name": ["Israel"], "2023": [54000]})
    path = tmp_path / "wide_missing.csv"
    raw.to_csv(path, index=False)

    source = _make_source(path.name)
    asset = DirectoryRawAcquirer().acquire(source, raw_root=tmp_path)[0]

    with pytest.raises(ValueError):
        WideYearMetricCsvAdapter().process([asset], source_spec=source)
