import pandas as pd
import pytest

from country_compare.data.examples import build_example_metric_dataframe
from country_compare.data.validation import (
    validate_and_parse_dataframe,
    validate_dataframe,
    validate_required_columns,
)


def test_validate_required_columns_passes():
    df = pd.DataFrame(
        columns=[
            "country_code",
            "country_name",
            "metric_id",
            "metric_name",
            "value",
            "year",
            "unit",
            "source_name",
            "source_url",
            "higher_is_better",
            "category",
        ]
    )

    issues = validate_required_columns(df)
    assert issues == []


def test_validate_dataframe_reports_missing_required_columns():
    df = pd.DataFrame(columns=["country_code", "country_name"])

    result = validate_dataframe(df)

    assert not result.valid
    assert any(issue.rule == "required_columns" for issue in result.issues)


def test_validate_and_parse_dataframe_raises_on_missing_required_columns():
    df = pd.DataFrame(columns=["country_code", "country_name"])

    with pytest.raises(ValueError, match="Missing required columns"):
        validate_and_parse_dataframe(df)


def test_example_dataset_is_valid():
    df = build_example_metric_dataframe()

    result = validate_dataframe(df)

    assert result.valid
