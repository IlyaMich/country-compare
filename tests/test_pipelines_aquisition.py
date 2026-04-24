from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from country_compare.pipelines.acquisition.directory import DirectoryRawAcquirer
from country_compare.pipelines.acquisition.remote import CompositeRawAcquirer, RemoteRawAcquirer
from country_compare.pipelines.errors import SourceNotFoundError
from country_compare.pipelines.models import SourceSpec


def test_directory_acquirer_resolves_single_csv_file(tmp_path: Path) -> None:
    path = tmp_path / "metrics.csv"
    pd.DataFrame({"x": [1]}).to_csv(path, index=False)

    source = SourceSpec(
        source_id="example",
        adapter_id="canonical_tabular_passthrough",
        path=path.name,
    )

    assets = DirectoryRawAcquirer().acquire(source, raw_root=tmp_path)

    assert len(assets) == 1
    assert assets[0].local_path == path.resolve()
    assert assets[0].file_format == "csv"
    assert assets[0].checksum


def test_directory_acquirer_raises_for_missing_file(tmp_path: Path) -> None:
    source = SourceSpec(
        source_id="missing",
        adapter_id="canonical_tabular_passthrough",
        path="does_not_exist.csv",
    )

    with pytest.raises(SourceNotFoundError):
        DirectoryRawAcquirer().acquire(source, raw_root=tmp_path)


def test_remote_raw_acquirer_materializes_file_url(tmp_path: Path) -> None:
    remote_source = tmp_path / 'remote.csv'
    pd.DataFrame({'x': [1]}).to_csv(remote_source, index=False)

    source = SourceSpec(
        source_id='remote_example',
        adapter_id='canonical_tabular_passthrough',
        remote_url=remote_source.resolve().as_uri(),
        download_filename='downloaded.csv',
    )

    assets = RemoteRawAcquirer().acquire(source, raw_root=tmp_path)

    assert len(assets) == 1
    assert assets[0].local_path.exists()
    assert assets[0].local_path.name == 'downloaded.csv'
    assert assets[0].file_format == 'csv'
    assert assets[0].metadata['remote_url'] == remote_source.resolve().as_uri()
    assert assets[0].metadata['acquisition_mode'] == 'remote_pull'


def test_composite_raw_acquirer_uses_remote_when_remote_url_is_present(tmp_path: Path) -> None:
    remote_source = tmp_path / 'remote.csv'
    pd.DataFrame({'x': [1]}).to_csv(remote_source, index=False)

    source = SourceSpec(
        source_id='remote_example',
        adapter_id='canonical_tabular_passthrough',
        remote_url=remote_source.resolve().as_uri(),
    )

    assets = CompositeRawAcquirer().acquire(source, raw_root=tmp_path)

    assert len(assets) == 1
    assert assets[0].local_path.exists()
    assert assets[0].metadata['acquisition_mode'] == 'remote_pull'