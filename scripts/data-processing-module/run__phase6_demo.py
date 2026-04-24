from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from tempfile import TemporaryDirectory

import pandas as pd
import yaml

from country_compare.data.ingestion.registry import has_source_adapter, list_registered_source_adapters
from country_compare.pipelines.acquisition.remote import CompositeRawAcquirer
from country_compare.pipelines.models import SourceSpec
from country_compare.pipelines.runners import run_processing_manifest


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


def _print_section(title: str) -> None:
    print(f"\n{'=' * 80}\n{title}\n{'=' * 80}")


def main() -> None:
    _print_section('1) Check built-in adapter registration')
    print('registered adapters:', list_registered_source_adapters())
    print('has canonical_tabular_passthrough:', has_source_adapter('canonical_tabular_passthrough'))
    print('has wide_year_metric_csv:', has_source_adapter('wide_year_metric_csv'))

    with TemporaryDirectory() as tmp_dir:
        root = Path(tmp_dir)
        remote_source_path = root / 'remote_input.csv'
        manifest_path = root / 'remote_manifest.yaml'
        audit_dir = root / 'audit_output'

        _make_valid_dataframe().to_csv(remote_source_path, index=False)

        _print_section('2) Demonstrate remote acquisition materialization')
        composite = CompositeRawAcquirer()
        assets = composite.acquire(
            SourceSpec(
                source_id='remote_demo',
                adapter_id='canonical_tabular_passthrough',
                remote_url=remote_source_path.resolve().as_uri(),
                download_filename='downloaded_remote.csv',
            ),
            raw_root=root,
        )
        for asset in assets:
            print(
                {
                    'source_id': asset.source_id,
                    'adapter_id': asset.adapter_id,
                    'local_path': str(asset.local_path),
                    'format': asset.file_format,
                    'size': asset.file_size,
                    'mode': asset.metadata.get('acquisition_mode'),
                    'remote_url': asset.metadata.get('remote_url'),
                }
            )

        manifest_path.write_text(
            yaml.safe_dump(
                {
                    'name': 'remote_demo_manifest',
                    'raw_root': str(root),
                    'processing': {
                        'publish': True,
                        'write_audit_artifacts': True,
                        'output_dir': str(audit_dir),
                    },
                    'defaults': {
                        'adapter_id': 'canonical_tabular_passthrough',
                        'source_name': 'Example Source',
                        'source_url': 'https://example.org/gdp',
                        'dataset_version': 'demo_remote_v1',
                    },
                    'sources': [
                        {
                            'source_id': 'remote_demo',
                            'remote_url': remote_source_path.resolve().as_uri(),
                            'download_filename': 'downloaded_remote.csv',
                            'tags': ['remote'],
                        }
                    ],
                },
                sort_keys=False,
            ),
            encoding='utf-8',
        )

        _print_section('3) Manifest-driven remote source success path')
        store = InMemoryStore()
        result = run_processing_manifest(manifest_path, store=store)
        print('result.ok:', result.ok)
        print('merge ok:', result.merge_report.ok if result.merge_report else None)
        print('validation ok:', result.validation_report.ok if result.validation_report else None)
        print('publication ok:', result.publication_report.ok if result.publication_report else None)
        print('audit written:', result.audit_report.written if result.audit_report else None)
        print('published rows:', 0 if store.written is None else len(store.written.index))
        if result.source_results:
            asset = result.source_results[0].assets[0]
            print('source tags:', result.source_results[0].tags)
            print('source asset mode:', asset.metadata.get('acquisition_mode'))
            print('source asset remote_url:', asset.metadata.get('remote_url'))

        _print_section('4) Phase E1 demo verdict')
        checks = {
            'adapters_registered': has_source_adapter('canonical_tabular_passthrough') and has_source_adapter('wide_year_metric_csv'),
            'remote_asset_materialized': len(assets) == 1 and assets[0].local_path.exists(),
            'remote_mode_tracked': bool(assets[0].metadata.get('acquisition_mode') == 'remote_pull'),
            'manifest_remote_success_ok': result.ok,
            'audit_written': bool(result.audit_report and result.audit_report.written),
            'publication_wrote_rows': bool(store.written is not None and len(store.written.index) == 2),
        }
        for key, value in checks.items():
            print(f'{key}: {value}')

        overall_ok = all(checks.values())
        print('\nOVERALL_PHASE_E1_DEMO:', 'PASS' if overall_ok else 'FAIL')
        if not overall_ok:
            raise SystemExit(1)


if __name__ == '__main__':
    main()