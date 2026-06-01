from __future__ import annotations

import pandas as pd
import pytest

from country_compare.data.contract import (
    ALL_COLUMNS,
    CANONICAL_SCHEMA,
    OPTIONAL_COLUMNS,
    PRIMARY_KEY_COLUMNS,
    REQUIRED_COLUMNS,
)
from country_compare.data.validation import (
    canonicalize_and_validate_dataframe,
    validate_dataframe,
)

pytestmark = pytest.mark.integration


def test_dataset_contains_required_canonical_columns(data_correctness_context) -> None:
    dataframe = data_correctness_context.dataframe

    missing_columns = [
        column for column in REQUIRED_COLUMNS if column not in dataframe.columns
    ]

    assert missing_columns == []


def test_canonical_contract_defines_expected_primary_key() -> None:
    assert PRIMARY_KEY_COLUMNS == ("country_code", "metric_id", "year")


def test_canonical_contract_required_columns_are_non_nullable_by_schema() -> None:
    nullable_required_columns = [
        column for column in REQUIRED_COLUMNS if CANONICAL_SCHEMA[column].nullable
    ]

    assert nullable_required_columns == []


def test_canonical_contract_optional_columns_are_nullable_by_schema() -> None:
    non_nullable_optional_columns = [
        column for column in OPTIONAL_COLUMNS if not CANONICAL_SCHEMA[column].nullable
    ]

    assert non_nullable_optional_columns == []


def test_dataset_has_no_missing_required_values(data_correctness_context) -> None:
    dataframe = data_correctness_context.dataframe

    missing_by_column = {
        column: int(dataframe[column].isna().sum())
        for column in REQUIRED_COLUMNS
        if column in dataframe.columns
    }

    assert {
        column: count for column, count in missing_by_column.items() if count > 0
    } == {}


def test_dataset_has_unique_primary_key_rows(data_correctness_context) -> None:
    dataframe = data_correctness_context.dataframe

    duplicate_mask = dataframe.duplicated(subset=list(PRIMARY_KEY_COLUMNS), keep=False)

    assert not duplicate_mask.any(), (
        dataframe.loc[
            duplicate_mask,
            list(PRIMARY_KEY_COLUMNS),
        ]
        .head(25)
        .to_dict("records")
    )


def test_dataset_passes_canonical_validation(data_correctness_context) -> None:
    dataframe = data_correctness_context.dataframe

    result = validate_dataframe(dataframe)

    assert result.valid, [issue.message for issue in result.issues]


def test_dataset_can_be_canonicalized_and_validated(data_correctness_context) -> None:
    dataframe = data_correctness_context.dataframe

    canonical = canonicalize_and_validate_dataframe(dataframe)

    assert list(canonical.columns[: len(ALL_COLUMNS)]) == list(ALL_COLUMNS)
    assert set(REQUIRED_COLUMNS).issubset(canonical.columns)


def test_canonicalized_dataset_has_expected_column_dtypes(
    data_correctness_context,
) -> None:
    dataframe = data_correctness_context.dataframe

    canonical = canonicalize_and_validate_dataframe(dataframe)

    assert pd.api.types.is_string_dtype(canonical["country_code"])
    assert pd.api.types.is_string_dtype(canonical["country_name"])
    assert pd.api.types.is_string_dtype(canonical["metric_id"])
    assert pd.api.types.is_string_dtype(canonical["metric_name"])
    assert pd.api.types.is_float_dtype(canonical["value"])
    assert pd.api.types.is_integer_dtype(canonical["year"])
    assert pd.api.types.is_string_dtype(canonical["unit"])
    assert pd.api.types.is_string_dtype(canonical["source_name"])
    assert pd.api.types.is_string_dtype(canonical["source_url"])
    assert pd.api.types.is_bool_dtype(canonical["higher_is_better"])
    assert pd.api.types.is_string_dtype(canonical["category"])


def test_country_codes_are_iso_alpha_3_like(data_correctness_context) -> None:
    dataframe = data_correctness_context.dataframe

    invalid_rows = dataframe[
        ~dataframe["country_code"].astype(str).str.fullmatch(r"[A-Z]{3}")
    ]

    assert invalid_rows.empty, (
        invalid_rows[["country_code", "country_name"]]
        .drop_duplicates()
        .head(25)
        .to_dict("records")
    )


def test_year_values_are_integral_and_in_supported_range(
    data_correctness_context,
) -> None:
    dataframe = data_correctness_context.dataframe

    years = pd.to_numeric(dataframe["year"], errors="coerce")

    invalid_rows = dataframe[
        years.isna() | (years % 1 != 0) | (years < 1900) | (years > 2100)
    ]

    assert invalid_rows.empty, (
        invalid_rows[["country_code", "metric_id", "year"]].head(25).to_dict("records")
    )


def test_values_are_numeric_and_finite(data_correctness_context) -> None:
    dataframe = data_correctness_context.dataframe

    values = pd.to_numeric(dataframe["value"], errors="coerce")
    invalid_rows = dataframe[values.isna() | values.isin([float("inf"), float("-inf")])]

    assert invalid_rows.empty, (
        invalid_rows[["country_code", "metric_id", "year", "value"]]
        .head(25)
        .to_dict("records")
    )
