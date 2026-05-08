from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Final

COUNTRY_CODE_COLUMN: Final[str] = "country_code"
COUNTRY_NAME_COLUMN: Final[str] = "country_name"
METRIC_ID_COLUMN: Final[str] = "metric_id"
METRIC_NAME_COLUMN: Final[str] = "metric_name"
VALUE_COLUMN: Final[str] = "value"
YEAR_COLUMN: Final[str] = "year"
UNIT_COLUMN: Final[str] = "unit"
SOURCE_NAME_COLUMN: Final[str] = "source_name"
SOURCE_URL_COLUMN: Final[str] = "source_url"
HIGHER_IS_BETTER_COLUMN: Final[str] = "higher_is_better"
CATEGORY_COLUMN: Final[str] = "category"

DATASET_VERSION_COLUMN: Final[str] = "dataset_version"
REGION_COLUMN: Final[str] = "region"
INCOME_GROUP_COLUMN: Final[str] = "income_group"
NOTES_COLUMN: Final[str] = "notes"

DEFAULT_MIN_YEAR: Final[int] = 1900
DEFAULT_MAX_YEAR: Final[int] = 2100

REQUIRED_COLUMNS: Final[tuple[str, ...]] = (
    COUNTRY_CODE_COLUMN,
    COUNTRY_NAME_COLUMN,
    METRIC_ID_COLUMN,
    METRIC_NAME_COLUMN,
    VALUE_COLUMN,
    YEAR_COLUMN,
    UNIT_COLUMN,
    SOURCE_NAME_COLUMN,
    SOURCE_URL_COLUMN,
    HIGHER_IS_BETTER_COLUMN,
    CATEGORY_COLUMN,
)

OPTIONAL_COLUMNS: Final[tuple[str, ...]] = (
    DATASET_VERSION_COLUMN,
    REGION_COLUMN,
    INCOME_GROUP_COLUMN,
    NOTES_COLUMN,
)

ALL_COLUMNS: Final[tuple[str, ...]] = REQUIRED_COLUMNS + OPTIONAL_COLUMNS

PRIMARY_KEY_COLUMNS: Final[tuple[str, ...]] = (
    COUNTRY_CODE_COLUMN,
    METRIC_ID_COLUMN,
    YEAR_COLUMN,
)


@dataclass(frozen=True)
class ColumnSpec:
    name: str
    pandas_dtype: str
    nullable: bool
    description: str


CANONICAL_SCHEMA: dict[str, ColumnSpec] = {
    COUNTRY_CODE_COLUMN: ColumnSpec(
        name=COUNTRY_CODE_COLUMN,
        pandas_dtype="string",
        nullable=False,
        description="ISO-3166-1 alpha-3 country code.",
    ),
    COUNTRY_NAME_COLUMN: ColumnSpec(
        name=COUNTRY_NAME_COLUMN,
        pandas_dtype="string",
        nullable=False,
        description="Human-readable country name.",
    ),
    METRIC_ID_COLUMN: ColumnSpec(
        name=METRIC_ID_COLUMN,
        pandas_dtype="string",
        nullable=False,
        description="Stable machine-readable metric identifier.",
    ),
    METRIC_NAME_COLUMN: ColumnSpec(
        name=METRIC_NAME_COLUMN,
        pandas_dtype="string",
        nullable=False,
        description="Human-readable metric name.",
    ),
    VALUE_COLUMN: ColumnSpec(
        name=VALUE_COLUMN,
        pandas_dtype="float64",
        nullable=False,
        description="Observed numeric value for country/metric/year.",
    ),
    YEAR_COLUMN: ColumnSpec(
        name=YEAR_COLUMN,
        pandas_dtype="Int64",
        nullable=False,
        description="Observation year.",
    ),
    UNIT_COLUMN: ColumnSpec(
        name=UNIT_COLUMN,
        pandas_dtype="string",
        nullable=False,
        description="Measurement unit, e.g. USD, index, score_0_10.",
    ),
    SOURCE_NAME_COLUMN: ColumnSpec(
        name=SOURCE_NAME_COLUMN,
        pandas_dtype="string",
        nullable=False,
        description="Data source display name.",
    ),
    SOURCE_URL_COLUMN: ColumnSpec(
        name=SOURCE_URL_COLUMN,
        pandas_dtype="string",
        nullable=False,
        description="Canonical source URL.",
    ),
    HIGHER_IS_BETTER_COLUMN: ColumnSpec(
        name=HIGHER_IS_BETTER_COLUMN,
        pandas_dtype="boolean",
        nullable=False,
        description="Whether a higher value indicates better performance.",
    ),
    CATEGORY_COLUMN: ColumnSpec(
        name=CATEGORY_COLUMN,
        pandas_dtype="string",
        nullable=False,
        description="Metric category such as economy or governance.",
    ),
    DATASET_VERSION_COLUMN: ColumnSpec(
        name=DATASET_VERSION_COLUMN,
        pandas_dtype="string",
        nullable=True,
        description="Optional version of the processed dataset.",
    ),
    REGION_COLUMN: ColumnSpec(
        name=REGION_COLUMN,
        pandas_dtype="string",
        nullable=True,
        description="Optional region classification.",
    ),
    INCOME_GROUP_COLUMN: ColumnSpec(
        name=INCOME_GROUP_COLUMN,
        pandas_dtype="string",
        nullable=True,
        description="Optional income classification.",
    ),
    NOTES_COLUMN: ColumnSpec(
        name=NOTES_COLUMN,
        pandas_dtype="string",
        nullable=True,
        description="Optional notes or caveats.",
    ),
}


def required_columns() -> list[str]:
    return list(REQUIRED_COLUMNS)


def optional_columns() -> list[str]:
    return list(OPTIONAL_COLUMNS)


def all_columns() -> list[str]:
    return list(ALL_COLUMNS)


def canonical_dtype_map() -> dict[str, str]:
    return {name: spec.pandas_dtype for name, spec in CANONICAL_SCHEMA.items()}


def nullable_columns() -> set[str]:
    return {name for name, spec in CANONICAL_SCHEMA.items() if spec.nullable}


def non_nullable_columns() -> set[str]:
    return {name for name, spec in CANONICAL_SCHEMA.items() if not spec.nullable}


def column_exists(name: str) -> bool:
    return name in CANONICAL_SCHEMA


def make_empty_record_dict() -> dict[str, Any]:
    return {col: None for col in ALL_COLUMNS}
