from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pandas as pd
import yaml

from country_compare.pipelines.runners import (
    load_processing_request_from_manifest,
    run_processing_manifest,
)


@dataclass
class InMemoryStore:
    backend_name: str = 'memory'
    path: str | None = None
    written: pd.DataFrame | None = None

    def read(self, columns: list[str] | None = None) -> pd.DataFrame:
        if self.written is None:
            return pd.DataFrame()
        if columns is None:
            return self.written.copy(deep=True)
        return self.written.loc[:, columns].copy(deep=True)

    def write(self, dataframe: pd.DataFrame) -> None:
        self.written = dataframe.copy(deep=True)

    def exists(self) -> bool:
        return self.written is not None

    def delete(self) -> None:
        self.written = None


def _make_valid_dataframe() -> pd.DataFrame:
    return pd.DataFrame(
        {
            'country_code': ['ISR', 'DEU'],
            'country_name': ['Israel', 'Germany'],
            'metric_id': ['gdp_per_capita', 'gdp_per_capita'],
            'metric_name': ['GDP per capita', 'GDP per capita'],
            'value': [54000.0, 65000.0],
            'year': [2023, 2023],
            'unit': ['USD', 'USD'],
            'source_name': ['Example Source', 'Example Source'],
            'source_url': ['https://example.org/gdp', 'https://example.org/gdp'],
            'higher_is_better': [True, True],
            'category': ['economy', 'economy'],
        }
    )


def test_load_processing_request_from_manifest_path_supports_overrides(tmp_path: Path) -> None:
    csv_path = tmp_path / 'canonical.csv'
    _make_valid_dataframe().to_csv(csv_path, index=False)
    manifest_path = tmp_path / 'sources.yaml'
    manifest_path.write_text(
        yaml.safe_dump(
            {
                'raw_root': str(tmp_path),
                'processing': {'publish': False},
                'defaults': {
                    'adapter_id': 'canonical_tabular_passthrough',
                    'source_name': 'Example Source',
                    'source_url': 'https://example.org/gdp',
                },
                'sources': [{'source_id': 'canonical_source', 'path': csv_path.name}],
            }
        ),
        encoding='utf-8',
    )

    request = load_processing_request_from_manifest(manifest_path, publish=True)

    assert request.raw_root == tmp_path
    assert request.publish is True
    assert len(request.sources) == 1
    assert request.sources[0].source_id == 'canonical_source'


def test_run_processing_manifest_path_succeeds_and_propagates_source_metadata(tmp_path: Path) -> None:
    csv_path = tmp_path / 'canonical.csv'
    _make_valid_dataframe().to_csv(csv_path, index=False)
    manifest_path = tmp_path / 'sources.yaml'
    manifest_path.write_text(
        yaml.safe_dump(
            {
                'raw_root': str(tmp_path),
                'tags': ['batch', 'manifest'],
                'labels': {'owner': 'qa'},
                'processing': {'publish': False},
                'defaults': {
                    'adapter_id': 'canonical_tabular_passthrough',
                    'source_name': 'Example Source',
                    'source_url': 'https://example.org/gdp',
                },
                'sources': [{'source_id': 'canonical_source', 'path': csv_path.name}],
            }
        ),
        encoding='utf-8',
    )

    result = run_processing_manifest(manifest_path)

    assert result.ok is True
    assert result.validation_report is not None and result.validation_report.ok is True
    assert result.merge_report is not None and result.merge_report.ok is True
    assert result.canonical_dataframe is not None
    assert len(result.source_results) == 1
    assert result.source_results[0].tags == ('batch', 'manifest')
    assert result.source_results[0].labels == {'owner': 'qa'}


def test_run_processing_manifest_allows_publish_override(tmp_path: Path) -> None:
    csv_path = tmp_path / 'canonical.csv'
    _make_valid_dataframe().to_csv(csv_path, index=False)
    manifest_path = tmp_path / 'sources.yaml'
    manifest_path.write_text(
        yaml.safe_dump(
            {
                'raw_root': str(tmp_path),
                'processing': {'publish': False},
                'defaults': {
                    'adapter_id': 'canonical_tabular_passthrough',
                    'source_name': 'Example Source',
                    'source_url': 'https://example.org/gdp',
                },
                'sources': [{'source_id': 'canonical_source', 'path': csv_path.name}],
            }
        ),
        encoding='utf-8',
    )
    store = InMemoryStore()

    result = run_processing_manifest(manifest_path, publish=True, store=store)

    assert result.ok is True
    assert result.publication_report is not None and result.publication_report.ok is True
    assert store.written is not None
    assert len(store.written.index) == 2