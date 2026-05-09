from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, TypeAlias

import pandas as pd

from country_compare.data.contract import (
    CATEGORY_COLUMN,
    COUNTRY_CODE_COLUMN,
    COUNTRY_NAME_COLUMN,
    METRIC_ID_COLUMN,
    METRIC_NAME_COLUMN,
    UNIT_COLUMN,
    YEAR_COLUMN,
)

CATALOG_FILENAME = "catalog.json"
CATALOG_SCHEMA_VERSION = "1.0"
MetadataCatalogPayload: TypeAlias = dict[str, Any]


@dataclass(frozen=True)
class CatalogValidationResult:
    valid: bool
    messages: tuple[str, ...] = ()


@dataclass(frozen=True)
class MetadataCatalog:
    schema_version: str
    dataset: dict[str, Any]
    identity: dict[str, Any]
    countries: tuple[dict[str, Any], ...]
    metrics: tuple[dict[str, Any], ...]
    years: tuple[int, ...]
    categories: tuple[dict[str, Any], ...]


def catalog_path_for_dataset(dataset_path: str | Path) -> Path:
    return Path(dataset_path).with_name(CATALOG_FILENAME)


def build_metadata_catalog(
    dataframe: pd.DataFrame,
    *,
    identity: dict[str, Any] | None = None,
) -> MetadataCatalogPayload:
    years = _extract_years(dataframe)
    year_min = min(years) if years else None
    year_max = max(years) if years else None
    countries = _build_countries(dataframe)
    metrics = _build_metrics(dataframe)
    categories = _build_categories(dataframe)
    return {
        "schema_version": CATALOG_SCHEMA_VERSION,
        "identity": dict(identity or {}),
        "dataset": {
            "row_count": int(len(dataframe.index)),
            "country_count": len(countries),
            "metric_count": len(metrics),
            "year_min": year_min,
            "year_max": year_max,
            "available_columns": [str(column) for column in dataframe.columns.tolist()],
        },
        "countries": countries,
        "metrics": metrics,
        "years": years,
        "categories": categories,
    }


def write_metadata_catalog(catalog: MetadataCatalogPayload, path: str | Path) -> None:
    Path(path).write_text(
        json.dumps(catalog, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def read_metadata_catalog(path: str | Path) -> MetadataCatalog:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    validation = validate_metadata_catalog(payload)
    if not validation.valid:
        raise ValueError("Invalid metadata catalog: " + "; ".join(validation.messages))
    return _catalog_from_payload(payload)


def validate_metadata_catalog(payload: Any) -> CatalogValidationResult:
    messages: list[str] = []
    if not isinstance(payload, dict):
        return CatalogValidationResult(False, ("catalog must be a JSON object",))
    if payload.get("schema_version") != CATALOG_SCHEMA_VERSION:
        messages.append(f"schema_version must be {CATALOG_SCHEMA_VERSION!r}")
    for key in ("dataset", "identity"):
        if not isinstance(payload.get(key), dict):
            messages.append(f"{key} must be an object")
    for key in ("countries", "metrics", "years", "categories"):
        if not isinstance(payload.get(key), list):
            messages.append(f"{key} must be a list")
    return CatalogValidationResult(not messages, tuple(messages))


def _catalog_from_payload(payload: MetadataCatalogPayload) -> MetadataCatalog:
    return MetadataCatalog(
        schema_version=str(payload["schema_version"]),
        dataset=dict(payload["dataset"]),
        identity=dict(payload.get("identity") or {}),
        countries=tuple(dict(item) for item in payload.get("countries", [])),
        metrics=tuple(dict(item) for item in payload.get("metrics", [])),
        years=tuple(int(year) for year in payload.get("years", [])),
        categories=tuple(dict(item) for item in payload.get("categories", [])),
    )


def _build_countries(dataframe: pd.DataFrame) -> list[dict[str, str]]:
    if dataframe.empty or not {COUNTRY_CODE_COLUMN, COUNTRY_NAME_COLUMN}.issubset(
        dataframe.columns
    ):
        return []
    pairs = (
        dataframe[[COUNTRY_CODE_COLUMN, COUNTRY_NAME_COLUMN]]
        .dropna(subset=[COUNTRY_CODE_COLUMN, COUNTRY_NAME_COLUMN])
        .drop_duplicates(subset=[COUNTRY_CODE_COLUMN])
        .sort_values([COUNTRY_NAME_COLUMN, COUNTRY_CODE_COLUMN])
    )
    return [
        {"code": str(row.country_code), "name": str(row.country_name)}
        for row in pairs.itertuples(index=False)
    ]


def _build_metrics(dataframe: pd.DataFrame) -> list[dict[str, Any]]:
    if dataframe.empty or not {METRIC_ID_COLUMN, METRIC_NAME_COLUMN}.issubset(
        dataframe.columns
    ):
        return []
    columns = [METRIC_ID_COLUMN, METRIC_NAME_COLUMN]
    if CATEGORY_COLUMN in dataframe.columns:
        columns.append(CATEGORY_COLUMN)
    if UNIT_COLUMN in dataframe.columns:
        columns.append(UNIT_COLUMN)
    metrics = (
        dataframe[columns]
        .dropna(subset=[METRIC_ID_COLUMN, METRIC_NAME_COLUMN])
        .drop_duplicates(subset=[METRIC_ID_COLUMN])
        .sort_values([METRIC_NAME_COLUMN, METRIC_ID_COLUMN])
    )
    output: list[dict[str, Any]] = []
    for row in metrics.itertuples(index=False):
        output.append(
            {
                "metric_id": str(getattr(row, METRIC_ID_COLUMN)),
                "display_name": str(getattr(row, METRIC_NAME_COLUMN)),
                "category": _optional_str(getattr(row, CATEGORY_COLUMN, None)),
                "unit": _optional_str(getattr(row, UNIT_COLUMN, None)),
            }
        )
    return output


def _build_categories(dataframe: pd.DataFrame) -> list[dict[str, Any]]:
    required = {CATEGORY_COLUMN, COUNTRY_CODE_COLUMN, METRIC_ID_COLUMN}
    if dataframe.empty or not required.issubset(dataframe.columns):
        return []
    grouped = (
        dataframe.dropna(subset=[CATEGORY_COLUMN])
        .groupby(CATEGORY_COLUMN, dropna=True)
        .agg(
            row_count=(CATEGORY_COLUMN, "size"),
            country_count=(COUNTRY_CODE_COLUMN, "nunique"),
            metric_count=(METRIC_ID_COLUMN, "nunique"),
        )
        .reset_index()
        .sort_values(["row_count", CATEGORY_COLUMN], ascending=[False, True])
    )
    return [
        {
            "name": str(row.category),
            "row_count": int(row.row_count),
            "country_count": int(row.country_count),
            "metric_count": int(row.metric_count),
        }
        for row in grouped.itertuples(index=False)
    ]


def _extract_years(dataframe: pd.DataFrame) -> list[int]:
    if dataframe.empty or YEAR_COLUMN not in dataframe.columns:
        return []
    numeric_years = pd.to_numeric(dataframe[YEAR_COLUMN], errors="coerce")
    return sorted(numeric_years.dropna().astype(int).unique().tolist())


def _optional_str(value: Any) -> str | None:
    if value is None or pd.isna(value):
        return None
    return str(value)
