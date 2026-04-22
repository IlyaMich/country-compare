from __future__ import annotations

import re
from collections.abc import Iterable, Mapping

import pandas as pd


def normalize_column_name(name: str) -> str:
    normalized = str(name).strip().lower()
    normalized = re.sub(r"[^a-z0-9]+", "_", normalized)
    normalized = re.sub(r"_+", "_", normalized).strip("_")
    return normalized


def normalize_columns(dataframe: pd.DataFrame) -> pd.DataFrame:
    result = dataframe.copy(deep=True)
    result.columns = [normalize_column_name(column) for column in result.columns]
    return result


def apply_column_mapping(dataframe: pd.DataFrame, mapping: Mapping[str, str] | None) -> pd.DataFrame:
    if not mapping:
        return dataframe.copy(deep=True)
    result = dataframe.copy(deep=True)
    result = result.rename(
        columns={normalize_column_name(source): target for source, target in mapping.items()}
    )
    return result


def find_column(
    columns: Iterable[str],
    *,
    preferred: str | None = None,
    aliases: Iterable[str] = (),
) -> str | None:
    normalized_columns = {normalize_column_name(column): str(column) for column in columns}

    candidates: list[str] = []
    if preferred:
        candidates.append(normalize_column_name(preferred))
    candidates.extend(normalize_column_name(alias) for alias in aliases)

    for candidate in candidates:
        if candidate in normalized_columns:
            return candidate
    return None
