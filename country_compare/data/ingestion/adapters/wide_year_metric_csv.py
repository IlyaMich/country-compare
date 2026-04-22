from __future__ import annotations

from typing import Any

import pandas as pd

from country_compare.data.contract import REQUIRED_COLUMNS
from country_compare.data.ingestion.base import AdapterResult, SourceAdapter
from country_compare.data.ingestion.registry import register_source_adapter
from country_compare.data.ingestion.transforms.canonical import add_optional_columns, order_canonical_columns
from country_compare.data.ingestion.transforms.columns import apply_column_mapping, find_column, normalize_columns
from country_compare.data.ingestion.transforms.metadata import stamp_metadata_defaults
from country_compare.data.ingestion.transforms.values import (
    coerce_boolean_scalar,
    coerce_numeric_series,
    detect_year_columns,
    parse_year_label,
)
from country_compare.pipelines.acquisition.tabular_readers import read_acquired_asset
from country_compare.pipelines.models import RowIssue

WIDE_YEAR_METRIC_CSV_ADAPTER_ID = "wide_year_metric_csv"


class WideYearMetricCsvAdapter(SourceAdapter):
    """Transform a simple wide year-column metric file into canonical long format."""

    COUNTRY_NAME_ALIASES = ("country_name", "country", "name")
    COUNTRY_CODE_ALIASES = ("country_code", "country_code_iso3", "iso3", "iso_3", "code")

    def process(self, assets: list[Any], *, source_spec: Any | None = None) -> AdapterResult:
        if not assets:
            raise ValueError("wide_year_metric_csv adapter received no acquired assets")
        if len(assets) != 1:
            raise ValueError(
                f"wide_year_metric_csv adapter expects exactly one asset, received {len(assets)}"
            )

        asset = assets[0]
        self.prepare(asset, source_spec=source_spec)
        read_options = getattr(source_spec, "read_options", None) or {}
        dataframe = read_acquired_asset(asset, read_options=read_options)
        return self._adapt_dataframe(dataframe, source_spec=source_spec)

    def to_standardized_dataframe(self) -> AdapterResult:  # pragma: no cover - compat path only
        asset = self.current_asset
        if asset is None:
            raise ValueError("no current asset was prepared for the wide_year_metric_csv adapter")
        dataframe = read_acquired_asset(asset, read_options={})
        return self._adapt_dataframe(dataframe, source_spec=self.current_source_spec)

    def _adapt_dataframe(self, dataframe: pd.DataFrame, *, source_spec: Any | None) -> AdapterResult:
        raw_row_count = int(len(dataframe.index))
        issues: list[RowIssue] = []
        warnings: list[str] = []

        normalized = normalize_columns(dataframe)
        mapping_overrides = getattr(source_spec, "mapping_overrides", None) or {}
        normalized = apply_column_mapping(normalized, mapping_overrides.get("columns", {}))

        country_name_column = find_column(
            list(normalized.columns),
            preferred=getattr(source_spec, "country_name_column", None),
            aliases=self.COUNTRY_NAME_ALIASES,
        )
        country_code_column = find_column(
            list(normalized.columns),
            preferred=getattr(source_spec, "country_code_column", None),
            aliases=self.COUNTRY_CODE_ALIASES,
        )

        missing_raw_columns = []
        if country_name_column is None:
            missing_raw_columns.append("country_name")
        if country_code_column is None:
            missing_raw_columns.append("country_code")
        if missing_raw_columns:
            raise ValueError(
                "wide_year_metric_csv adapter could not resolve required raw columns: "
                f"{missing_raw_columns}"
            )

        explicit_year_columns = getattr(source_spec, "year_columns", None)
        if explicit_year_columns:
            year_columns = [
                normalized_name
                for normalized_name in (str(value).strip().lower().replace(" ", "_") for value in explicit_year_columns)
                if normalized_name in normalized.columns
            ]
            missing_explicit = [
                value
                for value in explicit_year_columns
                if str(value).strip().lower().replace(" ", "_") not in normalized.columns
            ]
            if missing_explicit:
                warnings.append(f"ignored missing explicit year columns: {missing_explicit}")
        else:
            year_columns = detect_year_columns(list(normalized.columns))

        if not year_columns:
            raise ValueError("wide_year_metric_csv adapter could not detect any year columns")

        identifier_columns = [country_name_column, country_code_column]
        long_df = normalized.loc[:, [*identifier_columns, *year_columns]].melt(
            id_vars=identifier_columns,
            value_vars=year_columns,
            var_name="year_label",
            value_name="value",
        )

        blank_both_mask = (
            long_df[country_name_column].astype("string").str.strip().fillna("") == ""
        ) & (
            long_df[country_code_column].astype("string").str.strip().fillna("") == ""
        )
        for idx in long_df.index[blank_both_mask].tolist():
            issues.append(
                self._issue(
                    source_spec,
                    code="blank_country_row_dropped",
                    message="row had blank country_name and country_code",
                    row_identifier=str(idx),
                    columns=(country_name_column, country_code_column),
                    severity="warning",
                )
            )
        long_df = long_df.loc[~blank_both_mask].copy()

        long_df[country_name_column] = long_df[country_name_column].astype("string").str.strip()
        long_df[country_code_column] = long_df[country_code_column].astype("string").str.strip().str.upper()

        missing_country_code_mask = long_df[country_code_column].fillna("") == ""
        for idx in long_df.index[missing_country_code_mask].tolist():
            issues.append(
                self._issue(
                    source_spec,
                    code="missing_country_code_dropped",
                    message="row was dropped because country_code was blank",
                    row_identifier=str(idx),
                    columns=(country_code_column,),
                    severity="error",
                )
            )
        long_df = long_df.loc[~missing_country_code_mask].copy()

        long_df["year"] = long_df["year_label"].map(parse_year_label)
        invalid_year_mask = long_df["year"].isna()
        for idx in long_df.index[invalid_year_mask].tolist():
            issues.append(
                self._issue(
                    source_spec,
                    code="invalid_year_label_dropped",
                    message=f"row was dropped because year label could not be parsed: {long_df.at[idx, 'year_label']!r}",
                    row_identifier=str(idx),
                    columns=("year_label",),
                    severity="warning",
                )
            )
        long_df = long_df.loc[~invalid_year_mask].copy()

        numeric_values = coerce_numeric_series(long_df["value"])
        blank_value_mask = long_df["value"].isna() | long_df["value"].astype("string").str.strip().fillna("").eq("")
        invalid_numeric_mask = numeric_values.isna() & ~blank_value_mask
        for idx in long_df.index[blank_value_mask].tolist():
            issues.append(
                self._issue(
                    source_spec,
                    code="blank_value_dropped",
                    message="row was dropped because value was blank",
                    row_identifier=str(idx),
                    columns=("value",),
                    severity="warning",
                )
            )
        for idx in long_df.index[invalid_numeric_mask].tolist():
            issues.append(
                self._issue(
                    source_spec,
                    code="non_numeric_value_dropped",
                    message=f"row was dropped because value was not numeric: {long_df.at[idx, 'value']!r}",
                    row_identifier=str(idx),
                    columns=("value",),
                    severity="warning",
                )
            )
        keep_mask = ~(blank_value_mask | invalid_numeric_mask)
        long_df = long_df.loc[keep_mask].copy()
        numeric_values = numeric_values.loc[keep_mask]

        long_df = long_df.rename(
            columns={
                country_name_column: "country_name",
                country_code_column: "country_code",
            }
        )
        long_df["value"] = numeric_values.astype("float64")
        long_df["year"] = long_df["year"].astype("Int64")

        long_df = stamp_metadata_defaults(long_df, source_spec=source_spec)
        long_df = add_optional_columns(long_df)

        higher_is_better_value = getattr(source_spec, "higher_is_better", None)
        if higher_is_better_value is not None:
            resolved_hib = coerce_boolean_scalar(higher_is_better_value)
            if resolved_hib is None:
                raise ValueError("source_spec.higher_is_better could not be interpreted as boolean")
            long_df["higher_is_better"] = resolved_hib

        missing_required = [column for column in REQUIRED_COLUMNS if column not in long_df.columns]
        if missing_required:
            raise ValueError(
                "wide_year_metric_csv adapter could not produce required canonical columns: "
                f"{missing_required}"
            )

        required_metadata = [
            "metric_id",
            "metric_name",
            "unit",
            "source_name",
            "source_url",
            "higher_is_better",
            "category",
        ]
        missing_metadata = []
        for column in required_metadata:
            if column not in long_df.columns:
                missing_metadata.append(column)
                continue
            series = long_df[column]
            if series.isna().any():
                missing_metadata.append(column)
                continue
            if pd.api.types.is_string_dtype(series.dtype) or series.dtype == object:
                if series.astype("string").str.strip().eq("").any():
                    missing_metadata.append(column)
        if missing_metadata:
            raise ValueError(
                "wide_year_metric_csv adapter requires SourceSpec metadata for: "
                f"{sorted(set(missing_metadata))}"
            )

        result = long_df.drop(columns=["year_label"], errors="ignore")
        result = order_canonical_columns(result)
        return AdapterResult(
            dataframe=result,
            raw_row_count=raw_row_count,
            issues=issues,
            warnings=warnings,
        )

    @staticmethod
    def _issue(
        source_spec: Any | None,
        *,
        code: str,
        message: str,
        row_identifier: str,
        columns: tuple[str, ...],
        severity: str,
    ) -> RowIssue:
        return RowIssue(
            severity=severity,
            code=code,
            message=message,
            source_id=getattr(source_spec, "source_id", None),
            adapter_id=getattr(source_spec, "adapter_id", WIDE_YEAR_METRIC_CSV_ADAPTER_ID),
            row_identifier=row_identifier,
            columns=columns,
            action="dropped",
        )


register_source_adapter(
    WIDE_YEAR_METRIC_CSV_ADAPTER_ID,
    WideYearMetricCsvAdapter,
    description="Wide year-column CSV adapter for a single metric with per-country rows.",
    replace=True,
)
