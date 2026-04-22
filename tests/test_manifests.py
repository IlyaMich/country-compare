from __future__ import annotations

from pathlib import Path

from country_compare.pipelines.manifests import build_source_spec, load_source_manifest


def test_build_source_spec_deep_merges_mapping_overrides() -> None:
    spec = build_source_spec({'source_id': 'demo', 'adapter_id': 'wide_year_metric_csv', 'path': 'demo.csv', 'mapping_overrides': {'columns': {'Country Name': 'country_name'}}, 'tags': ['child']}, defaults={'mapping_overrides': {'columns': {'Country Code': 'country_code'}}, 'tags': ['base']})
    assert spec.mapping_overrides['columns'] == {'Country Code': 'country_code', 'Country Name': 'country_name'}
    assert spec.tags == ('base', 'child')


def test_load_source_manifest_accepts_list_root(tmp_path: Path) -> None:
    manifest_path = tmp_path / 'manifest.yaml'
    manifest_path.write_text('- source_id: demo\n  adapter_id: canonical_tabular_passthrough\n  path: demo.csv\n', encoding='utf-8')
    manifest = load_source_manifest(manifest_path)
    assert len(manifest.sources) == 1
    assert manifest.sources[0].source_id == 'demo'
