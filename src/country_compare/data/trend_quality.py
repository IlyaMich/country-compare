from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd
import yaml

REQUIRED_TREND_COLUMNS = {"country_code", "metric_id", "year", "value"}


def load_trend_rules(path: Path) -> dict[str, Any]:
    """Load metric-aware trend anomaly rules from YAML."""
    if not path.exists():
        raise FileNotFoundError(f"Trend rules file not found: {path}")

    content = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(content, dict):
        raise ValueError(f"Trend rules file must contain a mapping: {path}")

    return content


def _merged_metric_rule(rules: dict[str, Any], metric_id: str) -> dict[str, Any]:
    defaults = dict(rules.get("defaults") or {})
    metric_rules = dict((rules.get("metrics") or {}).get(metric_id) or {})

    merged = defaults | metric_rules
    merged.setdefault("enabled", True)
    merged.setdefault("require_consecutive_years", True)
    merged.setdefault("absolute_threshold", None)
    merged.setdefault("relative_threshold", None)
    merged.setdefault("relative_min_previous_abs", 1.0)

    return merged


def _review_key(anomaly: dict[str, Any]) -> tuple[str, str, int, int]:
    return (
        str(anomaly["country_code"]),
        str(anomaly["metric_id"]),
        int(anomaly["previous_year"]),
        int(anomaly["current_year"]),
    )


def _reviewed_keys(rules: dict[str, Any]) -> set[tuple[str, str, int, int]]:
    reviewed: set[tuple[str, str, int, int]] = set()

    for item in rules.get("reviewed_anomalies") or []:
        if not isinstance(item, dict):
            raise ValueError("Each reviewed anomaly entry must be a mapping.")

        reviewed.add(
            (
                str(item["country_code"]),
                str(item["metric_id"]),
                int(item["previous_year"]),
                int(item["current_year"]),
            )
        )

    return reviewed


def _sample(
    items: list[dict[str, Any]],
    max_examples: int | None,
) -> list[dict[str, Any]]:
    if max_examples is None:
        return items
    return items[:max_examples]


def scan_trend_anomalies(
    dataframe: pd.DataFrame,
    rules: dict[str, Any],
    *,
    max_examples: int | None = 25,
) -> dict[str, Any]:
    """Scan metric time series for unreviewed anomaly candidates.

    The scanner is intentionally metric-aware:

    - absolute thresholds are useful for bounded/percentage indicators;
    - relative thresholds are useful for positive scale/count/money metrics;
    - relative checks can ignore near-zero previous values;
    - nonconsecutive observations can be ignored when rules require true YoY checks;
    - known source-aligned anomalies can be documented in reviewed_anomalies.

    Returned anomalies are split into unreviewed and reviewed groups so release
    checks can fail only on new or undocumented anomalies.
    """
    missing_columns = sorted(REQUIRED_TREND_COLUMNS - set(dataframe.columns))
    if missing_columns:
        return {
            "missing_columns": missing_columns,
            "unreviewed_anomaly_count": 0,
            "reviewed_anomaly_count": 0,
            "sample_unreviewed_anomalies": [],
            "sample_reviewed_anomalies": [],
        }

    working = dataframe.loc[:, list(REQUIRED_TREND_COLUMNS)].copy()
    working["year"] = pd.to_numeric(working["year"], errors="coerce")
    working["value"] = pd.to_numeric(working["value"], errors="coerce")
    working = working.dropna(subset=["country_code", "metric_id", "year", "value"])

    reviewed = _reviewed_keys(rules)
    unreviewed_anomalies: list[dict[str, Any]] = []
    reviewed_anomalies: list[dict[str, Any]] = []

    for (country_code, metric_id), group in working.groupby(
        ["country_code", "metric_id"],
        sort=True,
    ):
        metric_id_text = str(metric_id)
        rule = _merged_metric_rule(rules, metric_id_text)

        if not bool(rule.get("enabled", True)):
            continue

        absolute_threshold = rule.get("absolute_threshold")
        relative_threshold = rule.get("relative_threshold")
        relative_min_previous_abs = float(rule.get("relative_min_previous_abs", 1.0))
        require_consecutive_years = bool(rule.get("require_consecutive_years", True))

        if absolute_threshold is None and relative_threshold is None:
            continue

        group = group.sort_values("year")
        previous_row: Any | None = None

        for row in group.itertuples(index=False):
            if previous_row is None:
                previous_row = row
                continue

            previous_year = int(previous_row.year)
            current_year = int(row.year)

            if require_consecutive_years and current_year - previous_year != 1:
                previous_row = row
                continue

            previous_value = float(previous_row.value)
            current_value = float(row.value)
            absolute_change = abs(current_value - previous_value)
            relative_change: float | None = None

            reasons: list[dict[str, float | str]] = []

            if absolute_threshold is not None:
                absolute_threshold_value = float(absolute_threshold)
                if absolute_change > absolute_threshold_value:
                    reasons.append(
                        {
                            "type": "absolute",
                            "observed": absolute_change,
                            "threshold": absolute_threshold_value,
                        }
                    )

            if (
                relative_threshold is not None
                and abs(previous_value) >= relative_min_previous_abs
            ):
                relative_threshold_value = float(relative_threshold)
                relative_change = absolute_change / abs(previous_value)

                if relative_change > relative_threshold_value:
                    reasons.append(
                        {
                            "type": "relative",
                            "observed": relative_change,
                            "threshold": relative_threshold_value,
                        }
                    )

            if reasons:
                anomaly = {
                    "country_code": str(country_code),
                    "metric_id": metric_id_text,
                    "previous_year": previous_year,
                    "current_year": current_year,
                    "previous_value": previous_value,
                    "current_value": current_value,
                    "absolute_change": absolute_change,
                    "relative_change": relative_change,
                    "reasons": reasons,
                }

                if _review_key(anomaly) in reviewed:
                    reviewed_anomalies.append(anomaly)
                else:
                    unreviewed_anomalies.append(anomaly)

            previous_row = row

    return {
        "missing_columns": [],
        "unreviewed_anomaly_count": len(unreviewed_anomalies),
        "reviewed_anomaly_count": len(reviewed_anomalies),
        "sample_unreviewed_anomalies": _sample(unreviewed_anomalies, max_examples),
        "sample_reviewed_anomalies": _sample(reviewed_anomalies, max_examples),
    }
