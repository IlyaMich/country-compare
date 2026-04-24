from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from country_compare.pipelines.engine import PipelineEngine
from country_compare.pipelines.manifests import load_source_manifest, manifest_to_processing_request
from country_compare.pipelines.models import ProcessingRequest, SourceSpec


class InMemoryStore:
    def __init__(self) -> None:
        self.backend_name = 'memory'
        self.path = None
        self.written: pd.DataFrame | None = None

    def write(self, dataframe: pd.DataFrame) -> None:
        self.written = dataframe.copy(deep=True)

    def read(self, columns: list[str] | None = None) -> pd.DataFrame:
        if self.written is None:
            return pd.DataFrame()
        if columns is None:
            return self.written.copy(deep=True)
        return self.written.loc[:, columns].copy(deep=True)

    def exists(self) -> bool:
        return self.written is not None

    def delete(self) -> None:
        self.written = None


@pytest.fixture()
def canonical_dataframe() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "country_code": ["ISR", "DEU"],
            "country_name": ["Israel", "Germany"],
            "metric_id": ["gdp_per_capita", "gdp_per_capita"],
            "metric_name": ["GDP per capita", "GDP per capita"],
            "value": [54000.0, 65000.0],
            "year": [2023, 2023],
            "unit": ["USD", "USD"],
            "source_name": ["Example Source", "Example Source"],
            "source_url": ["https://example.org/gdp", "https://example.org/gdp"],
            "higher_is_better": [True, True],
            "category": ["economy", "economy"],
        }
    )


def test_pipeline_run_succeeds_for_canonical_csv_input(
    tmp_path: Path,
    canonical_dataframe: pd.DataFrame,
) -> None:
    csv_path = tmp_path / "canonical.csv"
    canonical_dataframe.to_csv(csv_path, index=False)

    request = ProcessingRequest(
        sources=[
            SourceSpec(
                source_id="canonical_source",
                adapter_id="canonical_tabular_passthrough",
                path=csv_path.name,
                source_name="Example Source",
                source_url="https://example.org/gdp",
            )
        ],
        raw_root=tmp_path,
    )

    result = PipelineEngine().run(request)

    assert result.ok is True
    assert result.canonical_dataframe is not None
    assert len(result.canonical_dataframe.index) == 2
    assert result.validation_report is not None and result.validation_report.ok is True
    assert result.source_results[0].ok is True


def test_pipeline_run_fails_for_invalid_canonical_input(tmp_path: Path) -> None:
    invalid = pd.DataFrame(
        {
            "country_name": ["Israel"],
            "metric_id": ["gdp_per_capita"],
            "metric_name": ["GDP per capita"],
            "value": [54000.0],
            "year": [2023],
            "unit": ["USD"],
            "source_name": ["Example Source"],
            "source_url": ["https://example.org/gdp"],
            "higher_is_better": [True],
            "category": ["economy"],
        }
    )
    csv_path = tmp_path / "invalid.csv"
    invalid.to_csv(csv_path, index=False)

    request = ProcessingRequest(
        sources=[
            SourceSpec(
                source_id="invalid_source",
                adapter_id="canonical_tabular_passthrough",
                path=csv_path.name,
            )
        ],
        raw_root=tmp_path,
    )

    result = PipelineEngine().run(request)

    assert result.ok is False
    assert result.error is not None
    detailed_errors = list(result.validation_report.error_messages) if result.validation_report is not None else []
    detailed_errors.extend(result.warnings)
    assert any("country_code" in message for message in detailed_errors)


def test_pipeline_publishes_dataframe_via_store(
    tmp_path: Path,
    canonical_dataframe: pd.DataFrame,
) -> None:
    csv_path = tmp_path / "canonical.csv"
    canonical_dataframe.to_csv(csv_path, index=False)
    store = InMemoryStore()

    request = ProcessingRequest(
        sources=[
            SourceSpec(
                source_id="canonical_source",
                adapter_id="canonical_tabular_passthrough",
                path=csv_path.name,
            )
        ],
        raw_root=tmp_path,
        publish=True,
        store=store,
    )

    result = PipelineEngine().run(request)

    assert result.ok is True
    assert result.publication_report is not None and result.publication_report.ok is True
    assert store.written is not None
    assert len(store.written.index) == 2


def test_pipeline_surfaces_config_validation_failure(
    tmp_path: Path,
    canonical_dataframe: pd.DataFrame,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    csv_path = tmp_path / "canonical.csv"
    canonical_dataframe.to_csv(csv_path, index=False)

    import country_compare.config.validator as config_validator

    def fake_validate_metrics_against_dataframe(metrics, dataframe):
        raise ValueError("config/dataframe mismatch")

    monkeypatch.setattr(
        config_validator,
        "validate_metrics_against_dataframe",
        fake_validate_metrics_against_dataframe,
    )

    request = ProcessingRequest(
        sources=[
            SourceSpec(
                source_id="canonical_source",
                adapter_id="canonical_tabular_passthrough",
                path=csv_path.name,
            )
        ],
        raw_root=tmp_path,
        validate_against_config=True,
        metrics_config=object(),
    )

    result = PipelineEngine().run(request)

    assert result.ok is False
    assert result.validation_report is not None
    assert result.validation_report.config_checked is True
    assert any("config/dataframe mismatch" in message for message in result.validation_report.error_messages)


def test_pipeline_run_succeeds_for_wide_year_metric_csv_input(tmp_path: Path) -> None:
    raw = pd.DataFrame(
        {
            "Country Name": ["Israel", "Germany"],
            "Country Code": ["ISR", "DEU"],
            "2022": [52000, 61000],
            "2023": [54000, 65000],
        }
    )
    csv_path = tmp_path / "wide.csv"
    raw.to_csv(csv_path, index=False)

    request = ProcessingRequest(
        sources=[
            SourceSpec(
                source_id="wide_metric",
                adapter_id="wide_year_metric_csv",
                path=csv_path.name,
                metric_id="gdp_per_capita",
                metric_name="GDP per capita",
                unit="USD",
                category="economy",
                higher_is_better=True,
                source_name="Example Source",
                source_url="https://example.org/gdp",
            )
        ],
        raw_root=tmp_path,
    )

    result = PipelineEngine().run(request)

    assert result.ok is True
    assert result.canonical_dataframe is not None
    assert len(result.canonical_dataframe.index) == 4
    assert set(result.canonical_dataframe["year"].tolist()) == {2022, 2023}
    assert result.validation_report is not None and result.validation_report.ok is True


def test_pipeline_fails_when_merged_sources_create_duplicate_primary_keys(tmp_path: Path) -> None:
    raw = pd.DataFrame(
        {
            "Country Name": ["Israel"],
            "Country Code": ["ISR"],
            "2023": [54000],
        }
    )
    path_a = tmp_path / "wide_a.csv"
    path_b = tmp_path / "wide_b.csv"
    raw.to_csv(path_a, index=False)
    raw.to_csv(path_b, index=False)

    source_kwargs = dict(
        adapter_id="wide_year_metric_csv",
        metric_id="gdp_per_capita",
        metric_name="GDP per capita",
        unit="USD",
        category="economy",
        higher_is_better=True,
        source_name="Example Source",
        source_url="https://example.org/gdp",
    )

    request = ProcessingRequest(
        sources=[
            SourceSpec(source_id="a", path=path_a.name, **source_kwargs),
            SourceSpec(source_id="b", path=path_b.name, **source_kwargs),
        ],
        raw_root=tmp_path,
    )

    result = PipelineEngine().run(request)

    assert result.ok is False
    assert result.error is not None
    assert "duplicate canonical primary-key rows detected after merge" in result.error


def test_pipeline_reports_source_aware_merge_conflicts(tmp_path: Path, canonical_dataframe: pd.DataFrame) -> None:
    first_path = tmp_path / 'first.csv'
    second_path = tmp_path / 'second.csv'
    canonical_dataframe.iloc[[0]].to_csv(first_path, index=False)
    canonical_dataframe.iloc[[0]].to_csv(second_path, index=False)
    request = ProcessingRequest(
        sources=[
            SourceSpec(
                source_id='source_a',
                adapter_id='canonical_tabular_passthrough',
                path=first_path.name
            ),
            SourceSpec(
                source_id='source_b',
                adapter_id='canonical_tabular_passthrough',
                path=second_path.name
            )
        ],
        raw_root=tmp_path
    )
    result = PipelineEngine().run(request)
    assert result.ok is False
    assert result.merge_report is not None
    assert result.merge_report.ok is False
    assert result.merge_report.duplicate_key_conflict_count == 1
    assert result.merge_report.conflict_dataframe is not None
    assert set(result.merge_report.conflict_dataframe['_source_id'].tolist()) == {'source_a', 'source_b'}
    assert 'duplicate canonical primary-key rows detected after merge' in (result.error or '')


def test_manifest_loader_applies_defaults_and_builds_request(tmp_path: Path) -> None:
    manifest_path = tmp_path / 'sources.yaml'
    manifest_path.write_text('\n'.join(['name: demo_manifest', f'raw_root: {tmp_path.as_posix()}', 'processing:', '  write_audit_artifacts: true', 'defaults:', '  adapter_id: wide_year_metric_csv', '  source_name: Example Source', '  source_url: https://example.org/source', '  unit: USD', '  category: economy', '  metric_id: gdp_per_capita', '  metric_name: GDP per capita', '  higher_is_better: true', '  tags: [baseline]', 'sources:', '  - source_id: wb_gdp', '    path: wb.csv', '    tags: [world_bank]']), encoding='utf-8')
    manifest = load_source_manifest(manifest_path)
    request = manifest_to_processing_request(manifest)
    
    assert manifest.name == 'demo_manifest'
    assert request.write_audit_artifacts is True
    assert len(request.sources) == 1
    source = request.sources[0]
    assert source.adapter_id == 'wide_year_metric_csv'
    assert source.source_name == 'Example Source'
    assert source.tags == ('baseline', 'world_bank')


def test_pipeline_run_succeeds_for_remote_file_url_input(
    tmp_path: Path,
    canonical_dataframe: pd.DataFrame,
) -> None:
    remote_path = tmp_path / 'remote_canonical.csv'
    canonical_dataframe.to_csv(remote_path, index=False)

    request = ProcessingRequest(
        sources=[
            SourceSpec(
                source_id='remote_source',
                adapter_id='canonical_tabular_passthrough',
                remote_url=remote_path.resolve().as_uri(),
                download_filename='downloaded_canonical.csv',
                source_name='Example Source',
                source_url='https://example.org/gdp',
            )
        ],
        raw_root=tmp_path,
    )

    result = PipelineEngine().run(request)

    assert result.ok is True
    assert result.canonical_dataframe is not None
    assert len(result.canonical_dataframe.index) == 2
    assert result.source_results[0].assets[0].metadata['acquisition_mode'] == 'remote_pull'


def test_pipeline_manifest_path_supports_remote_url_sources(tmp_path: Path, canonical_dataframe: pd.DataFrame) -> None:
    remote_path = tmp_path / 'remote_manifest_source.csv'
    canonical_dataframe.to_csv(remote_path, index=False)
    manifest_path = tmp_path / 'sources.yaml'
    manifest_path.write_text(
        '\n'.join(
            [
                'name: remote_manifest',
                f'raw_root: {tmp_path.as_posix()}',
                'defaults:',
                '  adapter_id: canonical_tabular_passthrough',
                '  source_name: Example Source',
                '  source_url: https://example.org/gdp',
                'sources:',
                '  - source_id: remote_source',
                f'    remote_url: {remote_path.resolve().as_uri()}',
                '    download_filename: pulled.csv',
            ]
        ),
        encoding='utf-8',
    )

    request = manifest_to_processing_request(load_source_manifest(manifest_path))
    result = PipelineEngine().run(request)

    assert result.ok is True
    assert result.source_results[0].assets[0].local_path.name == 'pulled.csv'