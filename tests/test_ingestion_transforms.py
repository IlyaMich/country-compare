from __future__ import annotations

import pandas as pd

from country_compare.data.ingestion.transforms.columns import apply_column_mapping, normalize_columns
from country_compare.data.ingestion.transforms.metadata import stamp_metadata_defaults
from country_compare.data.ingestion.transforms.values import (
    coerce_boolean_scalar,
    coerce_numeric_series,
    detect_year_columns,
    parse_year_label,
)
from country_compare.pipelines.models import SourceSpec


def test_normalize_and_map_columns() -> None:
    dataframe = pd.DataFrame({"Country Name": ["Israel"], "Country Code": ["ISR"]})
    normalized = normalize_columns(dataframe)
    mapped = apply_column_mapping(normalized, {"country_code": "iso3"})
    assert list(mapped.columns) == ["country_name", "iso3"]


def test_detect_year_columns_and_parse_year_label() -> None:
    columns = ["country_name", "country_code", "2021", "2022", "notes"]
    assert detect_year_columns(columns) == ["2021", "2022"]
    assert parse_year_label("2023") == 2023
    assert parse_year_label("yr2023") is None


def test_coerce_numeric_and_boolean_helpers() -> None:
    series = pd.Series(["1", "x", None, "4.5"])
    coerced = coerce_numeric_series(series)
    assert coerced.tolist()[0] == 1.0
    assert pd.isna(coerced.tolist()[1])
    assert coerce_boolean_scalar("yes") is True
    assert coerce_boolean_scalar("0") is False
    assert coerce_boolean_scalar("maybe") is None


def test_stamp_metadata_defaults() -> None:
    dataframe = pd.DataFrame({"country_code": ["ISR"], "country_name": ["Israel"]})
    source = SourceSpec(
        source_id="example",
        adapter_id="wide_year_metric_csv",
        path="example.csv",
        metric_id="gdp_per_capita",
        metric_name="GDP per capita",
        unit="USD",
        category="economy",
        higher_is_better=True,
        source_name="Example Source",
        source_url="https://example.org/gdp",
    )
    stamped = stamp_metadata_defaults(dataframe, source_spec=source)
    assert stamped.loc[0, "metric_id"] == "gdp_per_capita"
    assert stamped.loc[0, "source_name"] == "Example Source"
    assert stamped.loc[0, "notes"] == "ingested_from=example.csv"
