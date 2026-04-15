from __future__ import annotations

from dataclasses import dataclass
from typing import Any

REQUIRED_COLUMNS: tuple[str, ...] = (
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
)

OPTIONAL_COLUMNS: tuple[str, ...] = (
    "dataset_version",
    "region",
    "income_group",
    "notes",
)

ALL_COLUMNS: tuple[str, ...] = REQUIRED_COLUMNS + OPTIONAL_COLUMNS

PRIMARY_KEY_COLUMNS: tuple[str, ...] = (
    "country_code",
    "metric_id",
    "year",
)


@dataclass(frozen=True)
class ColumnSpec:
    name: str
    pandas_dtype: str
    nullable: bool
    description: str


CANONICAL_SCHEMA: dict[str, ColumnSpec] = {
    "country_code": ColumnSpec(
        name="country_code",
        pandas_dtype="string",
        nullable=False,
        description="ISO-3166-1 alpha-3 country code.",
    ),
    "country_name": ColumnSpec(
        name="country_name",
        pandas_dtype="string",
        nullable=False,
        description="Human-readable country name.",
    ),
    "metric_id": ColumnSpec(
        name="metric_id",
        pandas_dtype="string",
        nullable=False,
        description="Stable machine-readable metric identifier.",
    ),
    "metric_name": ColumnSpec(
        name="metric_name",
        pandas_dtype="string",
        nullable=False,
        description="Human-readable metric name.",
    ),
    "value": ColumnSpec(
        name="value",
        pandas_dtype="float64",
        nullable=False,
        description="Observed numeric value for country/metric/year.",
    ),
    "year": ColumnSpec(
        name="year",
        pandas_dtype="Int64",
        nullable=False,
        description="Observation year.",
    ),
    "unit": ColumnSpec(
        name="unit",
        pandas_dtype="string",
        nullable=False,
        description="Measurement unit, e.g. USD, index, score_0_10.",
    ),
    "source_name": ColumnSpec(
        name="source_name",
        pandas_dtype="string",
        nullable=False,
        description="Data source display name.",
    ),
    "source_url": ColumnSpec(
        name="source_url",
        pandas_dtype="string",
        nullable=False,
        description="Canonical source URL.",
    ),
    "higher_is_better": ColumnSpec(
        name="higher_is_better",
        pandas_dtype="boolean",
        nullable=False,
        description="Whether a higher value indicates better performance.",
    ),
    "category": ColumnSpec(
        name="category",
        pandas_dtype="string",
        nullable=False,
        description="Metric category such as economy or governance.",
    ),
    "dataset_version": ColumnSpec(
        name="dataset_version",
        pandas_dtype="string",
        nullable=True,
        description="Optional version of the processed dataset.",
    ),
    "region": ColumnSpec(
        name="region",
        pandas_dtype="string",
        nullable=True,
        description="Optional region classification.",
    ),
    "income_group": ColumnSpec(
        name="income_group",
        pandas_dtype="string",
        nullable=True,
        description="Optional income classification.",
    ),
    "notes": ColumnSpec(
        name="notes",
        pandas_dtype="string",
        nullable=True,
        description="Optional notes or caveats.",
    ),
}


DEFAULT_MIN_YEAR = 1900
DEFAULT_MAX_YEAR = 2100


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
