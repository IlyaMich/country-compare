from __future__ import annotations

from pathlib import Path

import yaml

from country_compare.pipelines.manifests import load_source_manifest, manifest_to_processing_request


def test_load_source_manifest_inherits_manifest_tags_and_labels(tmp_path: Path) -> None:
    manifest_path = tmp_path / 'sources.yaml'
    manifest_path.write_text(
        yaml.safe_dump(
            {
                'name': 'demo_manifest',
                'raw_root': str(tmp_path),
                'tags': ['manifest', 'batch'],
                'labels': {'owner': 'data-team'},
                'defaults': {
                    'adapter_id': 'canonical_tabular_passthrough',
                    'source_name': 'Example Source',
                    'source_url': 'https://example.org/source',
                    'tags': ['defaults'],
                    'labels': {'env': 'test'},
                },
                'processing': {'publish': False},
                'sources': [
                    {
                        'source_id': 'dataset_a',
                        'path': 'dataset_a.csv',
                        'tags': ['source'],
                        'labels': {'table': 'metrics'},
                    }
                ],
            }
        ),
        encoding='utf-8',
    )

    manifest = load_source_manifest(manifest_path)

    assert manifest.name == 'demo_manifest'
    assert manifest.raw_root == tmp_path
    assert len(manifest.sources) == 1

    source = manifest.sources[0]
    assert source.source_id == 'dataset_a'
    assert source.adapter_id == 'canonical_tabular_passthrough'
    assert source.source_name == 'Example Source'
    assert source.source_url == 'https://example.org/source'
    assert source.tags == ('defaults', 'manifest', 'batch', 'source')
    assert source.labels == {
        'env': 'test',
        'owner': 'data-team',
        'table': 'metrics',
    }


def test_manifest_to_processing_request_uses_manifest_processing_defaults(tmp_path: Path) -> None:
    manifest_path = tmp_path / 'sources.yaml'
    manifest_path.write_text(
        yaml.safe_dump(
            {
                'raw_root': str(tmp_path),
                'processing': {
                    'publish': False,
                    'write_audit_artifacts': True,
                    'canonical_preview_rows': 3,
                },
                'defaults': {'adapter_id': 'canonical_tabular_passthrough'},
                'sources': [{'source_id': 'dataset_a', 'path': 'dataset_a.csv'}],
            }
        ),
        encoding='utf-8',
    )

    manifest = load_source_manifest(manifest_path)
    request = manifest_to_processing_request(manifest)

    assert request.raw_root == tmp_path
    assert request.publish is False
    assert request.write_audit_artifacts is True
    assert request.canonical_preview_rows == 3
    assert len(request.sources) == 1


def test_load_source_manifest_preserves_remote_source_fields(tmp_path: Path) -> None:
    payload = {
        'raw_root': str(tmp_path),
        'defaults': {'adapter_id': 'canonical_tabular_passthrough'},
        'sources': [
            {
                'source_id': 'remote_dataset',
                'remote_url': 'file:///tmp/example.csv',
                'download_filename': 'cached_example.csv',
            }
        ],
    }
    manifest_path = tmp_path / 'sources.yaml'
    manifest_path.write_text(yaml.safe_dump(payload), encoding='utf-8')

    manifest = load_source_manifest(manifest_path)

    assert len(manifest.sources) == 1
    source = manifest.sources[0]
    assert source.remote_url == 'file:///tmp/example.csv'
    assert source.download_filename == 'cached_example.csv'


def test_manifest_loader_preserves_world_bank_source_fields(tmp_path) -> None:
    manifest_path = tmp_path / "world_bank.yaml"
    manifest_payload = {
        "name": "world_bank_real_data",
        "raw_root": str(tmp_path),
        "defaults": {
            "adapter_id": "world_bank_indicator_csv",
            "source_name": "World Bank",
            "source_url": "https://data.worldbank.org/",
            "category": "TODO_CATEGORY",
            "unit": "TODO_UNIT",
            "higher_is_better": True,
            "filter_to_allowed_country_codes": True,
        },
        "sources": [
            {
                "source_id": "wb_gdp_current_usd",
                "path": "gdp_current_usd/wb_gdp_current_usd.csv",
                "metric_id": "gdp_current_usd",
                "metric_name": "GDP Current USD",
                "expected_indicator_code": "NY.GDP.MKTP.CD",
                "extra_allowed_country_codes": ["XKX"],
            }
        ],
    }
    manifest_path.write_text(yaml.safe_dump(manifest_payload), encoding="utf-8")

    manifest = load_source_manifest(manifest_path)
    source = manifest.sources[0]

    assert source.adapter_id == "world_bank_indicator_csv"
    assert source.expected_indicator_code == "NY.GDP.MKTP.CD"
    assert source.filter_to_allowed_country_codes is True
    assert source.extra_allowed_country_codes == ["XKX"]