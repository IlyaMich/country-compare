from __future__ import annotations

from typing import Any

import pandas as pd

from country_compare.data.contract import REQUIRED_COLUMNS
from country_compare.data.ingestion.base import SourceAdapter
from country_compare.data.ingestion.registry import register_source_adapter
from country_compare.data.ingestion.transforms.canonical import add_optional_columns, order_canonical_columns
from country_compare.data.ingestion.transforms.columns import apply_column_mapping, normalize_columns
from country_compare.data.ingestion.transforms.metadata import stamp_metadata_defaults
from country_compare.pipelines.acquisition.tabular_readers import read_acquired_asset

CANONICAL_TABULAR_PASSTHROUGH_ADAPTER_ID = "canonical_tabular_passthrough"


class CanonicalTabularPassthroughAdapter(SourceAdapter):
    """Minimal proving adapter for canonical or near-canonical tabular inputs."""

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
        normalized = normalize_columns(dataframe)
        mapping_overrides = getattr(source_spec, "mapping_overrides", None) or {}
        normalized = apply_column_mapping(normalized, mapping_overrides.get("columns", {}))
        normalized = add_optional_columns(normalized)
        normalized = stamp_metadata_defaults(normalized, source_spec=source_spec)

        missing_required = [column for column in REQUIRED_COLUMNS if column not in normalized.columns]
        if missing_required:
            raise ValueError(
                "passthrough adapter could not produce required canonical columns: "
                f"{missing_required}"
            )

        return order_canonical_columns(normalized)


register_source_adapter(
    CANONICAL_TABULAR_PASSTHROUGH_ADAPTER_ID,
    CanonicalTabularPassthroughAdapter,
    description="Canonical or near-canonical CSV/Parquet passthrough adapter.",
    replace=True,
)
