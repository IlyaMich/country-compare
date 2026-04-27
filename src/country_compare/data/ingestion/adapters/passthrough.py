from __future__ import annotations

import re
from typing import Any

import pandas as pd

from country_compare.data.contract import (
    ALL_COLUMNS,
    OPTIONAL_COLUMNS,
    REQUIRED_COLUMNS,
)
from country_compare.data.ingestion.base import SourceAdapter
from country_compare.data.ingestion.registry import register_source_adapter
from country_compare.data.ingestion.transforms.metadata import stamp_metadata_defaults
from country_compare.pipelines.acquisition.tabular_readers import read_acquired_asset

CANONICAL_TABULAR_PASSTHROUGH_ADAPTER_ID = "canonical_tabular_passthrough"


class CanonicalTabularPassthroughAdapter(SourceAdapter):
    def process(
        self, assets: list[Any], *, source_spec: Any | None = None
    ) -> pd.DataFrame:
        if not assets:
            raise ValueError("passthrough adapter received no acquired assets")
        if len(assets) != 1:
            raise ValueError(
                f"passthrough adapter expects exactly one asset, received {len(assets)}"
            )
        asset = assets[0]
        self.prepare(asset, source_spec=source_spec)
        dataframe = read_acquired_asset(
            asset, read_options=getattr(source_spec, "read_options", None) or {}
        )
        return self._normalize_to_canonical_columns(dataframe, source_spec=source_spec)

    def to_standardized_dataframe(self) -> pd.DataFrame:
        if self.current_asset is None:
            raise ValueError(
                "no current asset was prepared for the passthrough adapter"
            )
        dataframe = read_acquired_asset(self.current_asset, read_options={})
        return self._normalize_to_canonical_columns(
            dataframe, source_spec=self.current_source_spec
        )

    def _normalize_to_canonical_columns(
        self, dataframe: pd.DataFrame, *, source_spec: Any | None
    ) -> pd.DataFrame:
        frame = dataframe.copy(deep=True)
        frame.columns = [
            self._normalize_column_name(str(column)) for column in frame.columns
        ]
        mapping_overrides = getattr(source_spec, "mapping_overrides", None) or {}
        column_mapping = mapping_overrides.get("columns", {})
        if column_mapping:
            frame = frame.rename(
                columns={
                    self._normalize_column_name(source_column): target_column
                    for source_column, target_column in column_mapping.items()
                }
            )
        for column in OPTIONAL_COLUMNS:
            if column not in frame.columns:
                frame[column] = None
        frame = stamp_metadata_defaults(frame, source_spec=source_spec)
        missing_required = [
            column for column in REQUIRED_COLUMNS if column not in frame.columns
        ]
        if missing_required:
            raise ValueError(
                f"passthrough adapter could not produce required canonical columns: "
                f"{missing_required}"
            )
        ordered_columns = [column for column in ALL_COLUMNS if column in frame.columns]
        remaining_columns = [
            column for column in frame.columns if column not in ordered_columns
        ]
        return frame.loc[:, [*ordered_columns, *remaining_columns]].copy(deep=True)

    @staticmethod
    def _normalize_column_name(name: str) -> str:
        normalized = name.strip().lower()
        normalized = re.sub(r"[^a-z0-9]+", "_", normalized)
        return re.sub(r"_+", "_", normalized).strip("_")


register_source_adapter(
    CANONICAL_TABULAR_PASSTHROUGH_ADAPTER_ID,
    CanonicalTabularPassthroughAdapter,
    description="Canonical or near-canonical CSV/Parquet passthrough adapter.",
    replace=True,
)
