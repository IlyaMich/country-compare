from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from country_compare.pipelines.acquisition.directory import DirectoryRawAcquirer
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
