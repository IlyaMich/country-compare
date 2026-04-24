import pandas as pd

from country_compare.data.contract import REQUIRED_COLUMNS
from country_compare.data.examples import build_example_metric_dataframe
from country_compare.data.stores.parquet_store import ParquetMetricStore
from country_compare.data.validation import (
    validate_and_parse_dataframe,
    validate_dataframe,
)


def test_required_columns_present():
    assert "country_code" in REQUIRED_COLUMNS
    assert "metric_id" in REQUIRED_COLUMNS
    assert "value" in REQUIRED_COLUMNS
    assert "year" in REQUIRED_COLUMNS


def test_example_dataset_is_valid():
    df = build_example_metric_dataframe()
    result = validate_dataframe(df)
    assert result.valid, result.issues


def test_duplicate_primary_key_fails():
    df = build_example_metric_dataframe()
    duplicated = pd.concat([df, df.iloc[[0]]], ignore_index=True)

    result = validate_dataframe(duplicated)
    assert not result.valid
    assert any(issue.rule == "duplicates" for issue in result.issues)


def test_invalid_country_code_fails():
    df = build_example_metric_dataframe().copy()
    df.loc[0, "country_code"] = "Israel"

    result = validate_dataframe(df)
    assert not result.valid
    assert any(issue.rule == "country_code_format" for issue in result.issues)


def test_validate_and_parse_returns_dataset():
    df = build_example_metric_dataframe()
    dataset = validate_and_parse_dataframe(df)

    assert len(dataset.records) == len(df)


def test_parquet_store_roundtrip(tmp_path):
    df = build_example_metric_dataframe()

    store = ParquetMetricStore(tmp_path / "metrics.parquet")
    store.write_metrics(df)

    loaded = store.read_metrics()
    dataset = validate_and_parse_dataframe(loaded)

    assert len(dataset.records) == len(df)


def test_missing_required_column_fails():
    df = build_example_metric_dataframe().drop(columns=["metric_id"])

    result = validate_dataframe(df)
    assert not result.valid
    assert any(issue.rule == "required_columns" for issue in result.issues)


def test_invalid_year_fails():
    df = build_example_metric_dataframe().copy()
    df.loc[0, "year"] = 1800

    result = validate_dataframe(df)
    assert not result.valid
    assert any(issue.rule == "year_range" for issue in result.issues)
