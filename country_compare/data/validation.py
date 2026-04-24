from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

from country_compare.data.contract import (
    ALL_COLUMNS,
    CANONICAL_SCHEMA,
    DEFAULT_MAX_YEAR,
    DEFAULT_MIN_YEAR,
    PRIMARY_KEY_COLUMNS,
    REQUIRED_COLUMNS,
)
from country_compare.data.models import MetricDataset, MetricRecord


@dataclass(frozen=True)
class ValidationSettings:
    coerce_dtypes: bool = True
    normalize_columns: bool = True
    min_year: int = DEFAULT_MIN_YEAR
    max_year: int = DEFAULT_MAX_YEAR
    strict: bool = True


@dataclass
class ValidationIssue:
    rule: str
    message: str
    rows: list[int] = field(default_factory=list)
    column: str | None = None


@dataclass
class ValidationResult:
    valid: bool
    issues: list[ValidationIssue] = field(default_factory=list)

    def raise_if_invalid(self) -> None:
        if self.valid:
            return

        parts = []
        for issue in self.issues:
            col = f" column={issue.column}" if issue.column else ""
            rows = f" rows={issue.rows}" if issue.rows else ""
            parts.append(f"[{issue.rule}]{col}{rows}: {issue.message}")

        raise ValueError("Dataset validation failed:\n" + "\n".join(parts))


def normalize_canonical_columns(df: pd.DataFrame) -> pd.DataFrame:
    """
    Ensure canonical columns exist and appear first in canonical order.
    Extra columns are preserved after canonical columns.
    """
    result = df.copy()

    for col in ALL_COLUMNS:
        if col not in result.columns:
            result[col] = pd.NA

    canonical_first = list(ALL_COLUMNS)
    extras = [c for c in result.columns if c not in canonical_first]
    return result[canonical_first + extras]


def coerce_to_canonical_dtypes(df: pd.DataFrame) -> pd.DataFrame:
    """
    Coerce present columns into canonical pandas dtypes.
    """
    result = df.copy()

    for col, spec in CANONICAL_SCHEMA.items():
        if col not in result.columns:
            continue

        if spec.pandas_dtype == "string":
            result[col] = result[col].astype("string")
        elif spec.pandas_dtype == "float64":
            result[col] = pd.to_numeric(result[col], errors="coerce").astype("float64")
        elif spec.pandas_dtype == "Int64":
            result[col] = pd.to_numeric(result[col], errors="coerce").astype("Int64")
        elif spec.pandas_dtype == "boolean":
            result[col] = result[col].astype("boolean")

    return result


def validate_required_columns(df: pd.DataFrame) -> list[ValidationIssue]:
    missing = [col for col in REQUIRED_COLUMNS if col not in df.columns]
    if not missing:
        return []
    return [
        ValidationIssue(
            rule="required_columns",
            message=f"Missing required columns: {missing}",
        )
    ]


def validate_no_missing_required_values(df: pd.DataFrame) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []

    for col in REQUIRED_COLUMNS:
        if col not in df.columns:
            continue

        missing_mask = df[col].isna()
        if missing_mask.any():
            issues.append(
                ValidationIssue(
                    rule="missing_required_values",
                    column=col,
                    rows=df.index[missing_mask].tolist(),
                    message=f"Required column '{col}' contains missing values.",
                )
            )

    return issues


def validate_country_code_format(df: pd.DataFrame) -> list[ValidationIssue]:
    if "country_code" not in df.columns:
        return []

    series = df["country_code"].astype("string")
    invalid_mask = ~series.fillna("").str.fullmatch(r"[A-Z]{3}")
    invalid_mask = invalid_mask & series.notna()

    if not invalid_mask.any():
        return []

    return [
        ValidationIssue(
            rule="country_code_format",
            column="country_code",
            rows=df.index[invalid_mask].tolist(),
            message="country_code must be 3 uppercase letters (ISO alpha-3).",
        )
    ]


def validate_year_range(
    df: pd.DataFrame,
    min_year: int = DEFAULT_MIN_YEAR,
    max_year: int = DEFAULT_MAX_YEAR,
) -> list[ValidationIssue]:
    if "year" not in df.columns:
        return []

    year_numeric = pd.to_numeric(df["year"], errors="coerce")
    invalid_mask = (
        year_numeric.isna() | (year_numeric < min_year) | (year_numeric > max_year)
    )

    if not invalid_mask.any():
        return []

    return [
        ValidationIssue(
            rule="year_range",
            column="year",
            rows=df.index[invalid_mask].tolist(),
            message=f"year must be between {min_year} and {max_year}.",
        )
    ]


def validate_value_numeric_and_finite(df: pd.DataFrame) -> list[ValidationIssue]:
    if "value" not in df.columns:
        return []

    numeric_values = pd.to_numeric(df["value"], errors="coerce")
    invalid_mask = numeric_values.isna() | numeric_values.isin(
        [float("inf"), float("-inf")]
    )

    if not invalid_mask.any():
        return []

    return [
        ValidationIssue(
            rule="value_numeric",
            column="value",
            rows=df.index[invalid_mask].tolist(),
            message="value must be numeric and finite.",
        )
    ]


def validate_duplicates(df: pd.DataFrame) -> list[ValidationIssue]:
    if not all(col in df.columns for col in PRIMARY_KEY_COLUMNS):
        return []

    dup_mask = df.duplicated(subset=list(PRIMARY_KEY_COLUMNS), keep=False)
    if not dup_mask.any():
        return []

    return [
        ValidationIssue(
            rule="duplicates",
            rows=df.index[dup_mask].tolist(),
            message=f"Duplicate rows found for primary key {PRIMARY_KEY_COLUMNS}.",
        )
    ]


def validate_metric_consistency(df: pd.DataFrame) -> list[ValidationIssue]:
    required = {"metric_id", "metric_name", "unit", "higher_is_better", "category"}
    if not required.issubset(df.columns):
        return []

    issues: list[ValidationIssue] = []

    for metric_id, group in df.groupby("metric_id", dropna=False):
        if pd.isna(metric_id):
            continue

        for col in ("metric_name", "unit", "higher_is_better", "category"):
            distinct_values = group[col].dropna().astype(str).unique().tolist()
            if len(distinct_values) > 1:
                issues.append(
                    ValidationIssue(
                        rule="metric_consistency",
                        column=col,
                        rows=group.index.tolist(),
                        message=(
                            f"metric_id '{metric_id}' maps to multiple values in '{col}': "
                            f"{distinct_values}"
                        ),
                    )
                )

    return issues


def validate_source_url(df: pd.DataFrame) -> list[ValidationIssue]:
    if "source_url" not in df.columns:
        return []

    series = df["source_url"].astype("string")
    invalid_mask = ~series.fillna("").str.match(r"^https?://")
    invalid_mask = invalid_mask & series.notna()

    if not invalid_mask.any():
        return []

    return [
        ValidationIssue(
            rule="source_url",
            column="source_url",
            rows=df.index[invalid_mask].tolist(),
            message="source_url must start with http:// or https://",
        )
    ]


def validate_boolean_column(df: pd.DataFrame, column: str) -> list[ValidationIssue]:
    if column not in df.columns:
        return []

    invalid_rows: list[int] = []
    for idx, value in df[column].items():
        if pd.isna(value):
            invalid_rows.append(idx)
        elif value not in (True, False):
            invalid_rows.append(idx)

    if not invalid_rows:
        return []

    return [
        ValidationIssue(
            rule="boolean_type",
            column=column,
            rows=invalid_rows,
            message=f"{column} must contain boolean values only.",
        )
    ]


def validate_dataframe(
    df: pd.DataFrame,
    *,
    min_year: int = DEFAULT_MIN_YEAR,
    max_year: int = DEFAULT_MAX_YEAR,
) -> ValidationResult:
    issues: list[ValidationIssue] = []

    issues.extend(validate_required_columns(df))
    issues.extend(validate_no_missing_required_values(df))
    issues.extend(validate_country_code_format(df))
    issues.extend(validate_year_range(df, min_year=min_year, max_year=max_year))
    issues.extend(validate_value_numeric_and_finite(df))
    issues.extend(validate_duplicates(df))
    issues.extend(validate_metric_consistency(df))
    issues.extend(validate_source_url(df))
    issues.extend(validate_boolean_column(df, "higher_is_better"))

    return ValidationResult(valid=(len(issues) == 0), issues=issues)


def dataframe_to_metric_dataset(df: pd.DataFrame) -> MetricDataset:
    if not all(col in df.columns for col in REQUIRED_COLUMNS):
        raise ValueError(
            "Cannot build MetricDataset because required columns are missing."
        )

    records = []
    for row in df.to_dict(orient="records"):
        payload = {col: row.get(col) for col in ALL_COLUMNS if col in row}
        records.append(MetricRecord(**payload))

    return MetricDataset(records=records)


def metric_dataset_to_dataframe(dataset: MetricDataset) -> pd.DataFrame:
    rows = [record.model_dump(mode="json") for record in dataset.records]
    df = pd.DataFrame(rows)
    df = normalize_canonical_columns(df)
    df = coerce_to_canonical_dtypes(df)
    return df


def validate_and_parse_dataframe(
    df: pd.DataFrame,
    *,
    coerce_dtypes: bool = True,
    normalize_columns: bool = True,
    min_year: int = DEFAULT_MIN_YEAR,
    max_year: int = DEFAULT_MAX_YEAR,
) -> MetricDataset:
    working = df.copy()
    working = canonicalize_and_validate_dataframe(
        df,
        settings=ValidationSettings(
            coerce_dtypes=coerce_dtypes,
            normalize_columns=normalize_columns,
            min_year=min_year,
            max_year=max_year,
            strict=True,
        ),
    )
    return dataframe_to_metric_dataset(working)


def validate_dataframe_or_raise(
    df: pd.DataFrame,
    *,
    min_year: int = DEFAULT_MIN_YEAR,
    max_year: int = DEFAULT_MAX_YEAR,
) -> ValidationResult:
    result = validate_dataframe(df, min_year=min_year, max_year=max_year)
    result.raise_if_invalid()
    return result


def canonicalize_and_validate_dataframe(
    df: pd.DataFrame,
    *,
    settings: ValidationSettings | None = None,
) -> pd.DataFrame:
    settings = settings or ValidationSettings()
    working = df.copy()

    required_column_issues = validate_required_columns(working)
    if required_column_issues and settings.strict:
        ValidationResult(valid=False, issues=required_column_issues).raise_if_invalid()

    if settings.normalize_columns:
        working = normalize_canonical_columns(working)

    if settings.coerce_dtypes:
        working = coerce_to_canonical_dtypes(working)

    result = validate_dataframe(
        working,
        min_year=settings.min_year,
        max_year=settings.max_year,
    )

    if settings.strict:
        result.raise_if_invalid()

    return working


def prepare_dataframe_for_storage(
    df: pd.DataFrame,
    *,
    settings: ValidationSettings | None = None,
) -> pd.DataFrame:
    return canonicalize_and_validate_dataframe(df, settings=settings)


def prepare_dataframe_for_read(
    df: pd.DataFrame,
    *,
    settings: ValidationSettings | None = None,
) -> pd.DataFrame:
    return canonicalize_and_validate_dataframe(df, settings=settings)
