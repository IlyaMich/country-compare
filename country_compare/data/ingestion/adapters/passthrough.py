from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import pandas as pd

from country_compare.data.contract import ALL_COLUMNS, OPTIONAL_COLUMNS, REQUIRED_COLUMNS
from country_compare.data.ingestion.base import SourceAdapter
from country_compare.data.ingestion.registry import register_source_adapter
from country_compare.pipelines.acquisition.tabular_readers import read_acquired_asset

CANONICAL_TABULAR_PASSTHROUGH_ADAPTER_ID = "canonical_tabular_passthrough"


class CanonicalTabularPassthroughAdapter(SourceAdapter):
    """
    Minimal proving adapter for canonical or near-canonical tabular inputs.

    Expected use:
    - CSV / Parquet / Excel file already close to the canonical long format
    - optional column renames supplied through ``source_spec.mapping_overrides``
    - metadata stamps supplied through ``source_spec`` when absent in the file
    """

    def process(self, assets: list[Any], *, source_spec: Any | None = None) -> pd.DataFrame:
        if not assets:
            raise ValueError("passthrough adapter received no acquired assets")
        if len(assets) != 1:
            raise ValueError(
                f"passthrough adapter expects exactly one asset, received {len(assets)}"
            )

        asset = assets[0]
        self.prepare(asset, source_spec=source_spec)
        read_options = getattr(source_spec, "read_options", None) or {}
        dataframe = read_acquired_asset(asset, read_options=read_options)
        return self._normalize_to_canonical_columns(dataframe, source_spec=source_spec)

    def to_standardized_dataframe(self) -> pd.DataFrame:  # pragma: no cover - compat path only
        asset = self.current_asset
        if asset is None:
            raise ValueError("no current asset was prepared for the passthrough adapter")
        dataframe = read_acquired_asset(asset, read_options={})
        return self._normalize_to_canonical_columns(
            dataframe,
            source_spec=self.current_source_spec,
        )

    def _normalize_to_canonical_columns(
        self,
        dataframe: pd.DataFrame,
        *,
        source_spec: Any | None,
    ) -> pd.DataFrame:
        normalized = dataframe.copy(deep=True)
        normalized.columns = [self._normalize_column_name(str(column)) for column in normalized.columns]

        mapping_overrides = getattr(source_spec, "mapping_overrides", None) or {}
        column_mapping = mapping_overrides.get("columns", {})
        if column_mapping:
            normalized = normalized.rename(
                columns={
                    self._normalize_column_name(str(source_column)): target_column
                    for source_column, target_column in column_mapping.items()
                }
            )

        for column in OPTIONAL_COLUMNS:
            if column not in normalized.columns:
                normalized[column] = None

        self._stamp_metadata_defaults(normalized, source_spec=source_spec)

        missing_required = [column for column in REQUIRED_COLUMNS if column not in normalized.columns]
        if missing_required:
            raise ValueError(
                "passthrough adapter could not produce required canonical columns: "
                f"{missing_required}"
            )

        ordered_columns = [column for column in ALL_COLUMNS if column in normalized.columns]
        remaining_columns = [column for column in normalized.columns if column not in ordered_columns]
        return normalized.loc[:, [*ordered_columns, *remaining_columns]].copy(deep=True)

    @staticmethod
    def _normalize_column_name(name: str) -> str:
        normalized = name.strip().lower()
        normalized = re.sub(r"[^a-z0-9]+", "_", normalized)
        normalized = re.sub(r"_+", "_", normalized).strip("_")
        return normalized

    @staticmethod
    def _stamp_metadata_defaults(dataframe: pd.DataFrame, *, source_spec: Any | None) -> None:
        if source_spec is None:
            return

        defaults = {
            "source_name": getattr(source_spec, "source_name", None),
            "source_url": getattr(source_spec, "source_url", None),
            "dataset_version": getattr(source_spec, "dataset_version", None),
        }

        asset_path = getattr(getattr(source_spec, "metadata", {}), "get", lambda *_: None)("path")
        if asset_path is None and getattr(source_spec, "path", None) is not None:
            asset_path = str(getattr(source_spec, "path"))

        notes_default = None
        if asset_path is not None:
            notes_default = f"ingested_from={Path(str(asset_path)).name}"

        if "notes" not in dataframe.columns:
            dataframe["notes"] = notes_default
        elif notes_default is not None:
            dataframe["notes"] = dataframe["notes"].fillna(notes_default)

        for column, default_value in defaults.items():
            if default_value is None:
                continue
            if column not in dataframe.columns:
                dataframe[column] = default_value
                continue

            series = dataframe[column]
            if pd.api.types.is_string_dtype(series.dtype) or series.dtype == object:
                filled = series.replace("", pd.NA).fillna(default_value)
            else:
                filled = series.fillna(default_value)
            dataframe[column] = filled


register_source_adapter(
    CANONICAL_TABULAR_PASSTHROUGH_ADAPTER_ID,
    CanonicalTabularPassthroughAdapter,
    description="Canonical or near-canonical CSV/Parquet passthrough adapter.",
    replace=True,
)
