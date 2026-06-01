from __future__ import annotations

import argparse
import json
import math
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import pandas as pd

from country_compare.data.access import load_metric_dataframe
from country_compare.data.contract import PRIMARY_KEY_COLUMNS, REQUIRED_COLUMNS
from country_compare.data.validation import validate_dataframe


PASS = "PASS"
WARN = "WARN"
FAIL = "FAIL"


@dataclass(frozen=True)
class CorrectnessCheck:
    name: str
    status: str
    message: str
    details: dict[str, Any]


def _json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(k): _json_safe(v) for k, v in value.items()}

    if isinstance(value, list | tuple | set):
        return [_json_safe(v) for v in value]

    if value is pd.NA:
        return None

    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass

    if hasattr(value, "item"):
        try:
            return value.item()
        except ValueError:
            pass

    if isinstance(value, float) and not math.isfinite(value):
        return None

    return value


def _load_dataframe(data_path: Path | None) -> tuple[pd.DataFrame, str]:
    if data_path is None:
        return load_metric_dataframe(), "default metric store"

    # Important:
    # For correctness reporting, explicit --data-path must be read raw.
    # Invalid datasets still need a report file explaining what failed.
    # ParquetMetricStore.read() validates during read, which prevents the
    # report from being generated for intentionally invalid test fixtures.
    return pd.read_parquet(data_path), str(data_path)


def _check_schema(df: pd.DataFrame) -> CorrectnessCheck:
    missing = [column for column in REQUIRED_COLUMNS if column not in df.columns]
    extra = [column for column in df.columns if column not in REQUIRED_COLUMNS]

    if missing:
        return CorrectnessCheck(
            name="schema",
            status=FAIL,
            message=f"Missing required columns: {missing}",
            details={"missing_required_columns": missing, "extra_columns": extra},
        )

    return CorrectnessCheck(
        name="schema",
        status=PASS,
        message="All required canonical columns are present.",
        details={"required_columns": list(REQUIRED_COLUMNS), "extra_columns": extra},
    )


def _check_canonical_validation(df: pd.DataFrame) -> CorrectnessCheck:
    result = validate_dataframe(df)

    if result.valid:
        return CorrectnessCheck(
            name="canonical_validation",
            status=PASS,
            message="Dataset passed canonical validation.",
            details={"issue_count": 0, "issues": []},
        )

    issues = [asdict(issue) for issue in result.issues]
    return CorrectnessCheck(
        name="canonical_validation",
        status=FAIL,
        message=f"Dataset failed canonical validation with {len(issues)} issue(s).",
        details={"issue_count": len(issues), "issues": issues},
    )


def _check_primary_key_uniqueness(df: pd.DataFrame) -> CorrectnessCheck:
    missing_pk_columns = [column for column in PRIMARY_KEY_COLUMNS if column not in df.columns]
    if missing_pk_columns:
        return CorrectnessCheck(
            name="primary_key_uniqueness",
            status=FAIL,
            message=f"Cannot check primary key uniqueness; missing {missing_pk_columns}.",
            details={"missing_primary_key_columns": missing_pk_columns},
        )

    duplicate_mask = df.duplicated(subset=list(PRIMARY_KEY_COLUMNS), keep=False)
    duplicate_count = int(duplicate_mask.sum())

    if duplicate_count:
        sample = df.loc[duplicate_mask, list(PRIMARY_KEY_COLUMNS)].head(25).to_dict("records")
        return CorrectnessCheck(
            name="primary_key_uniqueness",
            status=FAIL,
            message=f"Found {duplicate_count} duplicate primary-key row(s).",
            details={
                "primary_key_columns": list(PRIMARY_KEY_COLUMNS),
                "duplicate_count": duplicate_count,
                "sample_duplicate_keys": sample,
            },
        )

    return CorrectnessCheck(
        name="primary_key_uniqueness",
        status=PASS,
        message="No duplicate country_code + metric_id + year rows found.",
        details={"primary_key_columns": list(PRIMARY_KEY_COLUMNS), "duplicate_count": 0},
    )


def _check_required_value_completeness(df: pd.DataFrame) -> CorrectnessCheck:
    missing_by_column: dict[str, int] = {}

    for column in REQUIRED_COLUMNS:
        if column not in df.columns:
            missing_by_column[column] = len(df)
            continue

        missing_by_column[column] = int(df[column].isna().sum())

    failing = {column: count for column, count in missing_by_column.items() if count > 0}

    if failing:
        return CorrectnessCheck(
            name="required_value_completeness",
            status=FAIL,
            message="One or more required columns contain missing values.",
            details={"missing_values_by_required_column": missing_by_column},
        )

    return CorrectnessCheck(
        name="required_value_completeness",
        status=PASS,
        message="Required columns contain no missing values.",
        details={"missing_values_by_required_column": missing_by_column},
    )


def _check_value_numeric_quality(df: pd.DataFrame) -> CorrectnessCheck:
    if "value" not in df.columns:
        return CorrectnessCheck(
            name="value_numeric_quality",
            status=FAIL,
            message="Cannot check numeric values; missing value column.",
            details={},
        )

    numeric_values = pd.to_numeric(df["value"], errors="coerce")
    invalid_mask = numeric_values.isna() | numeric_values.isin([float("inf"), float("-inf")])
    invalid_count = int(invalid_mask.sum())

    if invalid_count:
        sample = (
            df.loc[invalid_mask, ["country_code", "metric_id", "year", "value"]]
            .head(25)
            .to_dict("records")
        )
        return CorrectnessCheck(
            name="value_numeric_quality",
            status=FAIL,
            message=f"Found {invalid_count} non-numeric, missing, or infinite value(s).",
            details={"invalid_value_count": invalid_count, "sample_invalid_rows": sample},
        )

    return CorrectnessCheck(
        name="value_numeric_quality",
        status=PASS,
        message="All metric values are numeric and finite.",
        details={"invalid_value_count": 0},
    )


def _check_metric_metadata_consistency(df: pd.DataFrame) -> CorrectnessCheck:
    required_columns = {"metric_id", "metric_name", "unit", "higher_is_better", "category"}
    missing_columns = sorted(required_columns - set(df.columns))

    if missing_columns:
        return CorrectnessCheck(
            name="metric_metadata_consistency",
            status=FAIL,
            message=f"Cannot check metric metadata consistency; missing {missing_columns}.",
            details={"missing_columns": missing_columns},
        )

    inconsistent: list[dict[str, Any]] = []

    for metric_id, group in df.groupby("metric_id", dropna=False):
        for column in ("metric_name", "unit", "higher_is_better", "category"):
            distinct_values = sorted(str(value) for value in group[column].dropna().unique())
            if len(distinct_values) > 1:
                inconsistent.append(
                    {
                        "metric_id": metric_id,
                        "column": column,
                        "distinct_values": distinct_values,
                    }
                )

    if inconsistent:
        return CorrectnessCheck(
            name="metric_metadata_consistency",
            status=FAIL,
            message="Some metric IDs map to inconsistent metadata values.",
            details={"inconsistent_metric_metadata": inconsistent},
        )

    return CorrectnessCheck(
        name="metric_metadata_consistency",
        status=PASS,
        message="Each metric_id maps to one metric_name, unit, direction, and category.",
        details={"inconsistent_metric_metadata": []},
    )


def _check_coverage(df: pd.DataFrame) -> CorrectnessCheck:
    required_columns = {"country_code", "metric_id", "year"}
    missing_columns = sorted(required_columns - set(df.columns))

    if missing_columns:
        return CorrectnessCheck(
            name="coverage_summary",
            status=FAIL,
            message=f"Cannot build coverage summary; missing {missing_columns}.",
            details={"missing_columns": missing_columns},
        )

    years = pd.to_numeric(df["year"], errors="coerce").dropna()
    metric_counts = (
        df.groupby("metric_id", dropna=False)
        .agg(
            row_count=("metric_id", "size"),
            country_count=("country_code", "nunique"),
            year_count=("year", "nunique"),
        )
        .reset_index()
        .sort_values("metric_id")
    )

    return CorrectnessCheck(
        name="coverage_summary",
        status=PASS,
        message=(
            f"Dataset contains {len(df)} rows, "
            f"{df['country_code'].nunique()} countries, "
            f"{df['metric_id'].nunique()} metrics, "
            f"and {df['year'].nunique()} years."
        ),
        details={
            "row_count": int(len(df)),
            "country_count": int(df["country_code"].nunique()),
            "metric_count": int(df["metric_id"].nunique()),
            "year_count": int(df["year"].nunique()),
            "min_year": int(years.min()) if not years.empty else None,
            "max_year": int(years.max()) if not years.empty else None,
            "metrics": metric_counts.to_dict("records"),
        },
    )


def _check_trend_anomalies(
    df: pd.DataFrame,
    *,
    pct_change_warning_threshold: float,
    max_examples: int = 25,
) -> CorrectnessCheck:
    required_columns = {"country_code", "metric_id", "year", "value"}
    missing_columns = sorted(required_columns - set(df.columns))

    if missing_columns:
        return CorrectnessCheck(
            name="trend_anomaly_scan",
            status=FAIL,
            message=f"Cannot scan trend anomalies; missing {missing_columns}.",
            details={"missing_columns": missing_columns},
        )

    working = df.loc[:, ["country_code", "metric_id", "year", "value"]].copy()
    working["year"] = pd.to_numeric(working["year"], errors="coerce")
    working["value"] = pd.to_numeric(working["value"], errors="coerce")
    working = working.dropna(subset=["country_code", "metric_id", "year", "value"])

    anomalies: list[dict[str, Any]] = []

    for (country_code, metric_id), group in working.groupby(["country_code", "metric_id"]):
        group = group.sort_values("year")

        previous_year: int | None = None
        previous_value: float | None = None

        for row in group.itertuples(index=False):
            current_year = int(row.year)
            current_value = float(row.value)

            if previous_year is not None and previous_value is not None and previous_value != 0:
                pct_change = (current_value - previous_value) / abs(previous_value)

                if abs(pct_change) > pct_change_warning_threshold:
                    anomalies.append(
                        {
                            "country_code": country_code,
                            "metric_id": metric_id,
                            "previous_year": previous_year,
                            "current_year": current_year,
                            "previous_value": previous_value,
                            "current_value": current_value,
                            "pct_change": pct_change,
                        }
                    )

            previous_year = current_year
            previous_value = current_value

    if anomalies:
        return CorrectnessCheck(
            name="trend_anomaly_scan",
            status=WARN,
            message=(
                f"Found {len(anomalies)} year-over-year change(s) above "
                f"{pct_change_warning_threshold:.0%}. Review whether these are expected."
            ),
            details={
                "pct_change_warning_threshold": pct_change_warning_threshold,
                "anomaly_count": len(anomalies),
                "sample_anomalies": anomalies[:max_examples],
            },
        )

    return CorrectnessCheck(
        name="trend_anomaly_scan",
        status=PASS,
        message=(
            "No year-over-year value changes exceeded "
            f"{pct_change_warning_threshold:.0%}."
        ),
        details={
            "pct_change_warning_threshold": pct_change_warning_threshold,
            "anomaly_count": 0,
            "sample_anomalies": [],
        },
    )


def _overall_status(checks: list[CorrectnessCheck]) -> str:
    if any(check.status == FAIL for check in checks):
        return FAIL

    if any(check.status == WARN for check in checks):
        return WARN

    return PASS


def _escape_markdown_cell(value: object) -> str:
    return str(value).replace("|", "\\|").replace("\n", " ")


def _render_markdown_report(
    *,
    source: str,
    status: str,
    checks: list[CorrectnessCheck],
) -> str:
    lines = [
        "# Data Correctness Report",
        "",
        f"Overall status: **{status}**",
        "",
        f"Data source: `{source}`",
        "",
        "## Checks",
        "",
        "| Check | Status | Message |",
        "| --- | --- | --- |",
    ]

    for check in checks:
        lines.append(
            "| "
            + " | ".join(
                [
                    _escape_markdown_cell(check.name),
                    _escape_markdown_cell(check.status),
                    _escape_markdown_cell(check.message),
                ]
            )
            + " |"
        )

    coverage = next((check for check in checks if check.name == "coverage_summary"), None)
    if coverage is not None:
        lines.extend(
            [
                "",
                "## Dataset Summary",
                "",
                "```json",
                json.dumps(_json_safe(coverage.details), indent=2, sort_keys=True),
                "```",
            ]
        )

    failing_or_warning = [check for check in checks if check.status in {FAIL, WARN}]
    if failing_or_warning:
        lines.extend(["", "## Issues To Review", ""])

        for check in failing_or_warning:
            lines.extend(
                [
                    f"### {check.name} — {check.status}",
                    "",
                    check.message,
                    "",
                    "```json",
                    json.dumps(_json_safe(check.details), indent=2, sort_keys=True),
                    "```",
                    "",
                ]
            )

    return "\n".join(lines).rstrip() + "\n"


def _build_payload(
    *,
    source: str,
    status: str,
    checks: list[CorrectnessCheck],
) -> dict[str, Any]:
    return {
        "status": status,
        "source": source,
        "checks": [_json_safe(asdict(check)) for check in checks],
    }


def generate_report(
    *,
    data_path: Path | None,
    output: Path,
    json_output: Path | None,
    pct_change_warning_threshold: float,
) -> str:
    df, source = _load_dataframe(data_path)

    checks = [
        _check_schema(df),
        _check_canonical_validation(df),
        _check_primary_key_uniqueness(df),
        _check_required_value_completeness(df),
        _check_value_numeric_quality(df),
        _check_metric_metadata_consistency(df),
        _check_coverage(df),
        _check_trend_anomalies(
            df,
            pct_change_warning_threshold=pct_change_warning_threshold,
        ),
    ]

    status = _overall_status(checks)
    markdown = _render_markdown_report(source=source, status=status, checks=checks)

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(markdown, encoding="utf-8")

    if json_output is not None:
        json_output.parent.mkdir(parents=True, exist_ok=True)
        json_output.write_text(
            json.dumps(
                _json_safe(_build_payload(source=source, status=status, checks=checks)),
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )

    return status


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate a data correctness report for the canonical metric dataset.",
    )
    parser.add_argument(
        "--data-path",
        type=Path,
        default=None,
        help=(
            "Optional parquet dataset path. If omitted, the configured default "
            "country_compare metric store is used."
        ),
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("reports/data_correctness_report.md"),
        help="Markdown report output path.",
    )
    parser.add_argument(
        "--json-output",
        type=Path,
        default=None,
        help="Optional JSON report output path.",
    )
    parser.add_argument(
        "--pct-change-warning-threshold",
        type=float,
        default=0.50,
        help="Warn when year-over-year absolute percentage change exceeds this value.",
    )
    parser.add_argument(
        "--fail-on-warning",
        action="store_true",
        help="Return a non-zero exit code for WARN status as well as FAIL status.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(sys.argv[1:] if argv is None else argv)

    status = generate_report(
        data_path=args.data_path,
        output=args.output,
        json_output=args.json_output,
        pct_change_warning_threshold=args.pct_change_warning_threshold,
    )

    print(f"Data correctness report written to {args.output} with status {status}.")

    if status == FAIL:
        return 1

    if status == WARN and args.fail_on_warning:
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())