from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pandas as pd
import pytest

from data_update_service.orchestration.artifact_package import (
    FilesystemArtifactStore,
    build_dataset_version,
)
from data_update_service.orchestration.commands import RefreshCommand
from data_update_service.orchestration.diff import generate_diff_report
from data_update_service.orchestration.results import RefreshResult


def _dataframe() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "country_code": "ISR",
                "country_name": "Israel",
                "metric_id": "gdp_current_usd",
                "metric_name": "GDP Current USD",
                "value": 1.0,
                "year": 2025,
                "unit": "USD",
                "source_name": "World Bank",
                "source_url": "https://data.worldbank.org/",
                "higher_is_better": True,
                "category": "economy",
            }
        ]
    )


def test_build_dataset_version_uses_source_timestamp_and_hash_prefix() -> None:
    version = build_dataset_version(
        "world-bank",
        "abcdef1234567890",
        now=datetime(2026, 6, 13, 0, 8, 30, tzinfo=UTC),
    )

    assert version == "world_bank_2026-06-13T00-08-30Z_abcdef1"


def test_filesystem_artifact_store_writes_expected_package_files(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    command = RefreshCommand.create(
        source_family="world_bank",
        manifest_path="manifest.yaml",
        publish=True,
        dry_run=False,
    )
    dataframe = _dataframe()
    diff_report = generate_diff_report(dataframe)
    result = RefreshResult(
        job_id=command.job_id,
        command_id=command.command_id,
        source_family=command.source_family,
        status="completed",
        row_count=1,
        country_count=1,
        metric_count=1,
        year_min=2025,
        year_max=2025,
    )

    def fake_to_parquet(self: pd.DataFrame, path, index: bool = False) -> None:
        Path(path).write_bytes(b"fake-parquet")

    monkeypatch.setattr(pd.DataFrame, "to_parquet", fake_to_parquet)

    artifact = FilesystemArtifactStore(tmp_path).publish_package(
        command=command,
        dataframe=dataframe,
        validation_report={"ok": True},
        diff_report=diff_report,
        result_payload=result,
        now=datetime(2026, 6, 13, 0, 8, 30, tzinfo=UTC),
    )

    assert artifact.dataset_version.startswith("world_bank_2026-06-13T00-08-30Z_")
    assert (artifact.artifact_dir / "metrics.parquet").exists()
    assert (artifact.artifact_dir / "metrics_manifest.json").exists()
    assert (artifact.artifact_dir / "catalog.json").exists()
    assert (artifact.artifact_dir / "validation_report.json").exists()
    assert (artifact.artifact_dir / "diff_report.json").exists()
    assert (artifact.artifact_dir / "diff_report.md").exists()
    assert (artifact.artifact_dir / "source_audit.json").exists()
    assert (artifact.artifact_dir / "refresh_command.json").exists()
    assert (artifact.artifact_dir / "refresh_result.json").exists()
