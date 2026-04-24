from __future__ import annotations

from typing import Any

import pandas as pd

from country_compare.data.contract import REQUIRED_COLUMNS
from country_compare.data.ingestion.base import SourceAdapter
from country_compare.data.ingestion.registry import register_source_adapter
from country_compare.data.ingestion.transforms.canonical import add_optional_columns, order_canonical_columns
from country_compare.data.ingestion.transforms.columns import apply_column_mapping, find_column, normalize_columns
from country_compare.data.ingestion.transforms.metadata import stamp_metadata_defaults
from country_compare.data.ingestion.transforms.values import coerce_boolean_scalar, coerce_numeric_series, detect_year_columns, parse_year_label
from country_compare.pipelines.acquisition.tabular_readers import read_acquired_asset
from country_compare.pipelines.models import AdapterResult, RejectedRow, RowIssue

WIDE_YEAR_METRIC_CSV_ADAPTER_ID = 'wide_year_metric_csv'


class WideYearMetricCsvAdapter(SourceAdapter):
    COUNTRY_NAME_ALIASES = ('country_name', 'country', 'name')
    COUNTRY_CODE_ALIASES = ('country_code', 'country_code_iso3', 'iso3', 'iso_3', 'code')

    def process(self, assets: list[Any], *, source_spec: Any | None = None) -> AdapterResult:
        if not assets:
            raise ValueError('wide_year_metric_csv adapter received no acquired assets')
        if len(assets) != 1:
            raise ValueError(f'wide_year_metric_csv adapter expects exactly one asset, received {len(assets)}')
        asset = assets[0]
        self.prepare(asset, source_spec=source_spec)
        dataframe = read_acquired_asset(asset, read_options=getattr(source_spec, 'read_options', None) or {})
        return self._adapt_dataframe(dataframe, source_spec=source_spec)

    def to_standardized_dataframe(self) -> AdapterResult:
        if self.current_asset is None:
            raise ValueError('no current asset was prepared for the wide_year_metric_csv adapter')
        dataframe = read_acquired_asset(self.current_asset, read_options={})
        return self._adapt_dataframe(dataframe, source_spec=self.current_source_spec)

    def _adapt_dataframe(self, dataframe: pd.DataFrame, *, source_spec: Any | None) -> AdapterResult:
        raw_row_count = int(len(dataframe.index))
        issues: list[RowIssue] = []
        rejected_rows: list[RejectedRow] = []
        warnings: list[str] = []
        frame = normalize_columns(dataframe)
        mapping_overrides = getattr(source_spec, 'mapping_overrides', None) or {}
        frame = apply_column_mapping(frame, mapping_overrides.get('columns', {}))
        country_name_column = find_column(list(frame.columns), preferred=getattr(source_spec, 'country_name_column', None), aliases=self.COUNTRY_NAME_ALIASES)
        country_code_column = find_column(list(frame.columns), preferred=getattr(source_spec, 'country_code_column', None), aliases=self.COUNTRY_CODE_ALIASES)
        if country_name_column is None or country_code_column is None:
            missing = []
            if country_name_column is None:
                missing.append('country_name')
            if country_code_column is None:
                missing.append('country_code')
            raise ValueError(f'wide_year_metric_csv adapter could not resolve required raw columns: {missing}')
        explicit_year_columns = getattr(source_spec, 'year_columns', None)
        if explicit_year_columns:
            normalized_explicit = [str(value).strip().lower().replace(' ', '_') for value in explicit_year_columns]
            year_columns = [value for value in normalized_explicit if value in frame.columns]
            missing_explicit = [value for value in normalized_explicit if value not in frame.columns]
            if missing_explicit:
                warnings.append(f'ignored missing explicit year columns: {missing_explicit}')
        else:
            year_columns = detect_year_columns(list(frame.columns))
        if not year_columns:
            raise ValueError('wide_year_metric_csv adapter could not detect any year columns')
        long_df = frame.loc[:, [country_name_column, country_code_column, *year_columns]].melt(id_vars=[country_name_column, country_code_column], value_vars=year_columns, var_name='year_label', value_name='value')
        blank_country_mask = long_df[country_name_column].astype('string').str.strip().fillna('').eq('') & long_df[country_code_column].astype('string').str.strip().fillna('').eq('')
        for idx in long_df.index[blank_country_mask].tolist():
            issues.append(RowIssue(severity='warning', code='blank_country_row_dropped', message='row had blank country_name and country_code', source_id=getattr(source_spec, 'source_id', None), adapter_id=getattr(source_spec, 'adapter_id', WIDE_YEAR_METRIC_CSV_ADAPTER_ID), row_identifier=str(idx), columns=(country_name_column, country_code_column), action='dropped'))
            rejected_rows.append(RejectedRow(reason='blank_country_row_dropped', source_id=getattr(source_spec, 'source_id', None), adapter_id=getattr(source_spec, 'adapter_id', WIDE_YEAR_METRIC_CSV_ADAPTER_ID), row_identifier=str(idx), columns=(country_name_column, country_code_column), payload=long_df.loc[idx].to_dict()))
        long_df = long_df.loc[~blank_country_mask].copy()
        long_df[country_name_column] = long_df[country_name_column].astype('string').str.strip()
        long_df[country_code_column] = long_df[country_code_column].astype('string').str.strip().str.upper()
        missing_country_code_mask = long_df[country_code_column].fillna('').eq('')
        for idx in long_df.index[missing_country_code_mask].tolist():
            issues.append(RowIssue(severity='error', code='missing_country_code_dropped', message='row was dropped because country_code was blank', source_id=getattr(source_spec, 'source_id', None), adapter_id=getattr(source_spec, 'adapter_id', WIDE_YEAR_METRIC_CSV_ADAPTER_ID), row_identifier=str(idx), columns=(country_code_column,), action='dropped'))
            rejected_rows.append(RejectedRow(reason='missing_country_code_dropped', source_id=getattr(source_spec, 'source_id', None), adapter_id=getattr(source_spec, 'adapter_id', WIDE_YEAR_METRIC_CSV_ADAPTER_ID), row_identifier=str(idx), columns=(country_code_column,), payload=long_df.loc[idx].to_dict()))
        long_df = long_df.loc[~missing_country_code_mask].copy()
        long_df['year'] = long_df['year_label'].map(parse_year_label)
        invalid_year_mask = long_df['year'].isna()
        for idx in long_df.index[invalid_year_mask].tolist():
            issues.append(RowIssue(severity='warning', code='invalid_year_label_dropped', message=f"row was dropped because year label could not be parsed: {long_df.at[idx, 'year_label']!r}", source_id=getattr(source_spec, 'source_id', None), adapter_id=getattr(source_spec, 'adapter_id', WIDE_YEAR_METRIC_CSV_ADAPTER_ID), row_identifier=str(idx), columns=('year_label',), action='dropped'))
            rejected_rows.append(RejectedRow(reason='invalid_year_label_dropped', source_id=getattr(source_spec, 'source_id', None), adapter_id=getattr(source_spec, 'adapter_id', WIDE_YEAR_METRIC_CSV_ADAPTER_ID), row_identifier=str(idx), columns=('year_label',), payload=long_df.loc[idx].to_dict()))
        long_df = long_df.loc[~invalid_year_mask].copy()
        numeric_values = coerce_numeric_series(long_df['value'])
        blank_value_mask = long_df['value'].isna() | long_df['value'].astype('string').str.strip().fillna('').eq('')
        invalid_numeric_mask = numeric_values.isna() & ~blank_value_mask
        for idx in long_df.index[blank_value_mask].tolist():
            issues.append(RowIssue(severity='warning', code='blank_value_dropped', message='row was dropped because value was blank', source_id=getattr(source_spec, 'source_id', None), adapter_id=getattr(source_spec, 'adapter_id', WIDE_YEAR_METRIC_CSV_ADAPTER_ID), row_identifier=str(idx), columns=('value',), action='dropped'))
            rejected_rows.append(RejectedRow(reason='blank_value_dropped', source_id=getattr(source_spec, 'source_id', None), adapter_id=getattr(source_spec, 'adapter_id', WIDE_YEAR_METRIC_CSV_ADAPTER_ID), row_identifier=str(idx), columns=('value',), payload=long_df.loc[idx].to_dict()))
        for idx in long_df.index[invalid_numeric_mask].tolist():
            issues.append(RowIssue(severity='warning', code='non_numeric_value_dropped', message=f"row was dropped because value was not numeric: {long_df.at[idx, 'value']!r}", source_id=getattr(source_spec, 'source_id', None), adapter_id=getattr(source_spec, 'adapter_id', WIDE_YEAR_METRIC_CSV_ADAPTER_ID), row_identifier=str(idx), columns=('value',), action='dropped'))
            rejected_rows.append(RejectedRow(reason='non_numeric_value_dropped', source_id=getattr(source_spec, 'source_id', None), adapter_id=getattr(source_spec, 'adapter_id', WIDE_YEAR_METRIC_CSV_ADAPTER_ID), row_identifier=str(idx), columns=('value',), payload=long_df.loc[idx].to_dict()))
        keep_mask = ~(blank_value_mask | invalid_numeric_mask)
        long_df = long_df.loc[keep_mask].copy()
        numeric_values = numeric_values.loc[keep_mask]
        long_df = long_df.rename(columns={country_name_column: 'country_name', country_code_column: 'country_code'})
        long_df['value'] = numeric_values.astype('float64')
        long_df['year'] = long_df['year'].astype('Int64')
        long_df = stamp_metadata_defaults(long_df, source_spec=source_spec)
        long_df = add_optional_columns(long_df)
        higher_is_better_value = getattr(source_spec, 'higher_is_better', None)
        if higher_is_better_value is not None:
            resolved = coerce_boolean_scalar(higher_is_better_value)
            if resolved is None:
                raise ValueError('source_spec.higher_is_better could not be interpreted as boolean')
            long_df['higher_is_better'] = resolved
        missing_required = [column for column in REQUIRED_COLUMNS if column not in long_df.columns]
        if missing_required:
            raise ValueError(f'wide_year_metric_csv adapter could not produce required canonical columns: {missing_required}')
        required_metadata = ['metric_id', 'metric_name', 'unit', 'source_name', 'source_url', 'higher_is_better', 'category']
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
                if series.astype('string').str.strip().eq('').any():
                    missing_metadata.append(column)
        if missing_metadata:
            raise ValueError(f'wide_year_metric_csv adapter requires SourceSpec metadata for: {sorted(set(missing_metadata))}')
        result = long_df.drop(columns=['year_label'], errors='ignore')
        result = order_canonical_columns(result)
        return AdapterResult(dataframe=result, raw_row_count=raw_row_count, issues=issues, rejected_rows=rejected_rows, warnings=warnings)


register_source_adapter(WIDE_YEAR_METRIC_CSV_ADAPTER_ID, WideYearMetricCsvAdapter, description='Wide year-column CSV adapter for a single metric with per-country rows.', replace=True)
