from __future__ import annotations

from typing import Any

import pandas as pd

from country_compare.data.contract import REQUIRED_COLUMNS
from country_compare.data.ingestion.base import SourceAdapter
from country_compare.data.ingestion.registry import register_source_adapter
from country_compare.data.ingestion.transforms.canonical import add_optional_columns, order_canonical_columns
from country_compare.data.ingestion.transforms.columns import apply_column_mapping, find_column, normalize_columns
from country_compare.data.ingestion.transforms.geographies import resolve_allowed_country_codes
from country_compare.data.ingestion.transforms.metadata import stamp_metadata_defaults
from country_compare.data.ingestion.transforms.values import (
    coerce_boolean_scalar,
    coerce_numeric_series,
    detect_year_columns,
    parse_year_label,
)
from country_compare.pipelines.acquisition.tabular_readers import read_acquired_asset
from country_compare.pipelines.models import AdapterResult, RejectedRow, RowIssue

WORLD_BANK_INDICATOR_CSV_ADAPTER_ID = "world_bank_indicator_csv"


class WorldBankIndicatorCsvAdapter(SourceAdapter):
    COUNTRY_NAME_ALIASES = ("country_name", "country", "name")
    COUNTRY_CODE_ALIASES = ("country_code", "country_code_iso3", "iso3", "iso_3", "code")
    INDICATOR_NAME_ALIASES = ("indicator_name",)
    INDICATOR_CODE_ALIASES = ("indicator_code",)

    def process(self, assets: list[Any], *, source_spec: Any | None = None) -> AdapterResult:
        if not assets:
            raise ValueError("world_bank_indicator_csv adapter received no acquired assets")
        if len(assets) != 1:
            raise ValueError(
                f"world_bank_indicator_csv adapter expects exactly one asset, received {len(assets)}"
            )
        asset = assets[0]
        self.prepare(asset, source_spec=source_spec)
        read_options = dict(getattr(source_spec, "read_options", None) or {})
        read_options.setdefault("skiprows", 4)
        dataframe = read_acquired_asset(asset, read_options=read_options)
        return self._adapt_dataframe(dataframe, source_spec=source_spec)

    def to_standardized_dataframe(self) -> AdapterResult:
        if self.current_asset is None:
            raise ValueError("no current asset was prepared for the world_bank_indicator_csv adapter")
        dataframe = read_acquired_asset(self.current_asset, read_options={"skiprows": 4})
        return self._adapt_dataframe(dataframe, source_spec=self.current_source_spec)

    def _adapt_dataframe(self, dataframe: pd.DataFrame, *, source_spec: Any | None) -> AdapterResult:
        raw_row_count = int(len(dataframe.index))
        issues: list[RowIssue] = []
        rejected_rows: list[RejectedRow] = []
        warnings: list[str] = []

        frame = normalize_columns(dataframe)
        mapping_overrides = getattr(source_spec, "mapping_overrides", None) or {}
        frame = apply_column_mapping(frame, mapping_overrides.get("columns", {}))

        country_name_column = find_column(
            list(frame.columns),
            preferred=getattr(source_spec, "country_name_column", None),
            aliases=self.COUNTRY_NAME_ALIASES,
        )
        country_code_column = find_column(
            list(frame.columns),
            preferred=getattr(source_spec, "country_code_column", None),
            aliases=self.COUNTRY_CODE_ALIASES,
        )
        indicator_name_column = find_column(
            list(frame.columns),
            preferred=None,
            aliases=self.INDICATOR_NAME_ALIASES,
        )
        indicator_code_column = find_column(
            list(frame.columns),
            preferred=None,
            aliases=self.INDICATOR_CODE_ALIASES,
        )

        missing = []
        if country_name_column is None:
            missing.append("country_name")
        if country_code_column is None:
            missing.append("country_code")
        if indicator_name_column is None:
            missing.append("indicator_name")
        if indicator_code_column is None:
            missing.append("indicator_code")
        if missing:
            raise ValueError(
                f"world_bank_indicator_csv adapter could not resolve required raw columns: {missing}"
            )

        frame[country_code_column] = frame[country_code_column].astype("string").str.strip().str.upper()
        frame[country_name_column] = frame[country_name_column].astype("string").str.strip()

        observed_indicator_codes = sorted(
            {
                str(value).strip()
                for value in frame[indicator_code_column].dropna().unique().tolist()
                if str(value).strip()
            }
        )
        if not observed_indicator_codes:
            raise ValueError("world_bank_indicator_csv adapter found no non-blank indicator_code values")
        if len(observed_indicator_codes) != 1:
            raise ValueError(
                "world_bank_indicator_csv adapter expected exactly one indicator_code value, "
                f"found: {observed_indicator_codes}"
            )

        expected_indicator_code = getattr(source_spec, "expected_indicator_code", None)
        if expected_indicator_code is not None and observed_indicator_codes[0] != str(expected_indicator_code).strip():
            raise ValueError(
                "world_bank_indicator_csv adapter indicator_code mismatch: "
                f"expected {expected_indicator_code!r}, observed {observed_indicator_codes[0]!r}"
            )

        filter_to_allowed = getattr(source_spec, "filter_to_allowed_country_codes", True)
        if filter_to_allowed:
            allowed_codes = resolve_allowed_country_codes(
                allowed_country_codes=getattr(source_spec, "allowed_country_codes", None),
                extra_allowed_country_codes=getattr(source_spec, "extra_allowed_country_codes", None),
            )
            supported_mask = frame[country_code_column].isin(allowed_codes)
            for idx in frame.index[~supported_mask].tolist():
                issues.append(
                    RowIssue(
                        severity="warning",
                        code="unsupported_country_code_dropped",
                        message=(
                            "row was dropped because country_code is outside the supported "
                            "country-code universe"
                        ),
                        source_id=getattr(source_spec, "source_id", None),
                        adapter_id=getattr(source_spec, "adapter_id", WORLD_BANK_INDICATOR_CSV_ADAPTER_ID),
                        row_identifier=str(idx),
                        columns=(country_name_column, country_code_column),
                        action="dropped",
                    )
                )
                rejected_rows.append(
                    RejectedRow(
                        reason="unsupported_country_code_dropped",
                        source_id=getattr(source_spec, "source_id", None),
                        adapter_id=getattr(source_spec, "adapter_id", WORLD_BANK_INDICATOR_CSV_ADAPTER_ID),
                        row_identifier=str(idx),
                        columns=(country_name_column, country_code_column),
                        payload=frame.loc[idx].to_dict(),
                    )
                )
            frame = frame.loc[supported_mask].copy()

        explicit_year_columns = getattr(source_spec, "year_columns", None)
        if explicit_year_columns:
            normalized_explicit = [str(value).strip().lower().replace(" ", "_") for value in explicit_year_columns]
            year_columns = [value for value in normalized_explicit if value in frame.columns]
            missing_explicit = [value for value in normalized_explicit if value not in frame.columns]
            if missing_explicit:
                warnings.append(f"ignored missing explicit year columns: {missing_explicit}")
        else:
            year_columns = detect_year_columns(list(frame.columns))

        if not year_columns:
            raise ValueError("world_bank_indicator_csv adapter could not detect any year columns")

        long_df = frame.loc[:, [country_name_column, country_code_column, *year_columns]].melt(
            id_vars=[country_name_column, country_code_column],
            value_vars=year_columns,
            var_name="year_label",
            value_name="value",
        )

        blank_country_mask = (
            long_df[country_name_column].astype("string").str.strip().fillna("").eq("")
            & long_df[country_code_column].astype("string").str.strip().fillna("").eq("")
        )
        for idx in long_df.index[blank_country_mask].tolist():
            issues.append(
                RowIssue(
                    severity="warning",
                    code="blank_country_row_dropped",
                    message="row had blank country_name and country_code",
                    source_id=getattr(source_spec, "source_id", None),
                    adapter_id=getattr(source_spec, "adapter_id", WORLD_BANK_INDICATOR_CSV_ADAPTER_ID),
                    row_identifier=str(idx),
                    columns=(country_name_column, country_code_column),
                    action="dropped",
                )
            )
            rejected_rows.append(
                RejectedRow(
                    reason="blank_country_row_dropped",
                    source_id=getattr(source_spec, "source_id", None),
                    adapter_id=getattr(source_spec, "adapter_id", WORLD_BANK_INDICATOR_CSV_ADAPTER_ID),
                    row_identifier=str(idx),
                    columns=(country_name_column, country_code_column),
                    payload=long_df.loc[idx].to_dict(),
                )
            )
        long_df = long_df.loc[~blank_country_mask].copy()

        missing_country_code_mask = long_df[country_code_column].fillna("").eq("")
        for idx in long_df.index[missing_country_code_mask].tolist():
            issues.append(
                RowIssue(
                    severity="error",
                    code="missing_country_code_dropped",
                    message="row was dropped because country_code was blank",
                    source_id=getattr(source_spec, "source_id", None),
                    adapter_id=getattr(source_spec, "adapter_id", WORLD_BANK_INDICATOR_CSV_ADAPTER_ID),
                    row_identifier=str(idx),
                    columns=(country_code_column,),
                    action="dropped",
                )
            )
            rejected_rows.append(
                RejectedRow(
                    reason="missing_country_code_dropped",
                    source_id=getattr(source_spec, "source_id", None),
                    adapter_id=getattr(source_spec, "adapter_id", WORLD_BANK_INDICATOR_CSV_ADAPTER_ID),
                    row_identifier=str(idx),
                    columns=(country_code_column,),
                    payload=long_df.loc[idx].to_dict(),
                )
            )
        long_df = long_df.loc[~missing_country_code_mask].copy()

        long_df["year"] = long_df["year_label"].map(parse_year_label)
        invalid_year_mask = long_df["year"].isna()
        for idx in long_df.index[invalid_year_mask].tolist():
            issues.append(
                RowIssue(
                    severity="warning",
                    code="invalid_year_label_dropped",
                    message=(
                        "row was dropped because year label could not be parsed: "
                        f"{long_df.at[idx, 'year_label']!r}"
                    ),
                    source_id=getattr(source_spec, "source_id", None),
                    adapter_id=getattr(source_spec, "adapter_id", WORLD_BANK_INDICATOR_CSV_ADAPTER_ID),
                    row_identifier=str(idx),
                    columns=("year_label",),
                    action="dropped",
                )
            )
            rejected_rows.append(
                RejectedRow(
                    reason="invalid_year_label_dropped",
                    source_id=getattr(source_spec, "source_id", None),
                    adapter_id=getattr(source_spec, "adapter_id", WORLD_BANK_INDICATOR_CSV_ADAPTER_ID),
                    row_identifier=str(idx),
                    columns=("year_label",),
                    payload=long_df.loc[idx].to_dict(),
                )
            )
        long_df = long_df.loc[~invalid_year_mask].copy()

        numeric_values = coerce_numeric_series(long_df["value"])
        blank_value_mask = long_df["value"].isna() | long_df["value"].astype("string").str.strip().fillna("").eq("")
        invalid_numeric_mask = numeric_values.isna() & ~blank_value_mask

        for idx in long_df.index[blank_value_mask].tolist():
            issues.append(
                RowIssue(
                    severity="warning",
                    code="blank_value_dropped",
                    message="row was dropped because value was blank",
                    source_id=getattr(source_spec, "source_id", None),
                    adapter_id=getattr(source_spec, "adapter_id", WORLD_BANK_INDICATOR_CSV_ADAPTER_ID),
                    row_identifier=str(idx),
                    columns=("value",),
                    action="dropped",
                )
            )
            rejected_rows.append(
                RejectedRow(
                    reason="blank_value_dropped",
                    source_id=getattr(source_spec, "source_id", None),
                    adapter_id=getattr(source_spec, "adapter_id", WORLD_BANK_INDICATOR_CSV_ADAPTER_ID),
                    row_identifier=str(idx),
                    columns=("value",),
                    payload=long_df.loc[idx].to_dict(),
                )
            )

        for idx in long_df.index[invalid_numeric_mask].tolist():
            issues.append(
                RowIssue(
                    severity="warning",
                    code="non_numeric_value_dropped",
                    message=f"row was dropped because value was not numeric: {long_df.at[idx, 'value']!r}",
                    source_id=getattr(source_spec, "source_id", None),
                    adapter_id=getattr(source_spec, "adapter_id", WORLD_BANK_INDICATOR_CSV_ADAPTER_ID),
                    row_identifier=str(idx),
                    columns=("value",),
                    action="dropped",
                )
            )
            rejected_rows.append(
                RejectedRow(
                    reason="non_numeric_value_dropped",
                    source_id=getattr(source_spec, "source_id", None),
                    adapter_id=getattr(source_spec, "adapter_id", WORLD_BANK_INDICATOR_CSV_ADAPTER_ID),
                    row_identifier=str(idx),
                    columns=("value",),
                    payload=long_df.loc[idx].to_dict(),
                )
            )

        keep_mask = ~(blank_value_mask | invalid_numeric_mask)
        long_df = long_df.loc[keep_mask].copy()
        numeric_values = numeric_values.loc[keep_mask]

        long_df = long_df.rename(columns={country_name_column: "country_name", country_code_column: "country_code"})
        long_df["value"] = numeric_values.astype("float64")
        long_df["year"] = long_df["year"].astype("Int64")

        long_df = stamp_metadata_defaults(long_df, source_spec=source_spec)
        long_df = add_optional_columns(long_df)

        higher_is_better_value = getattr(source_spec, "higher_is_better", None)
        if higher_is_better_value is not None:
            resolved = coerce_boolean_scalar(higher_is_better_value)
            if resolved is None:
                raise ValueError("source_spec.higher_is_better could not be interpreted as boolean")
            long_df["higher_is_better"] = resolved

        missing_required = [column for column in REQUIRED_COLUMNS if column not in long_df.columns]
        if missing_required:
            raise ValueError(
                "world_bank_indicator_csv adapter could not produce required canonical columns: "
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
                "world_bank_indicator_csv adapter requires SourceSpec metadata for: "
                f"{sorted(set(missing_metadata))}"
            )

        result = long_df.drop(columns=["year_label"], errors="ignore")
        result = order_canonical_columns(result)
        return AdapterResult(
            dataframe=result,
            raw_row_count=raw_row_count,
            issues=issues,
            rejected_rows=rejected_rows,
            warnings=warnings,
        )


register_source_adapter(
    WORLD_BANK_INDICATOR_CSV_ADAPTER_ID,
    WorldBankIndicatorCsvAdapter,
    description=(
        "World Bank indicator-page CSV adapter with indicator validation and "
        "supported-country filtering."
    ),
    replace=True,
)
