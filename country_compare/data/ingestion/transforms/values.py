from __future__ import annotations

import re
from typing import Any

import pandas as pd


_YEAR_LABEL_PATTERN = re.compile(r"^(?P<year>19\d{2}|20\d{2}|2100)$")


def parse_year_label(label: Any) -> int | None:
    text = str(label).strip().lower()
    match = _YEAR_LABEL_PATTERN.fullmatch(text)
    if match is None:
        return None
    return int(match.group("year"))


def detect_year_columns(columns: list[str]) -> list[str]:
    return [column for column in columns if parse_year_label(column) is not None]


def coerce_numeric_series(series: pd.Series) -> pd.Series:
    return pd.to_numeric(series, errors="coerce")


def coerce_boolean_scalar(value: Any) -> bool | None:
    if pd.isna(value):
        return None
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if text in {"true", "1", "yes", "y", "t"}:
        return True
    if text in {"false", "0", "no", "n", "f"}:
        return False
    return None
