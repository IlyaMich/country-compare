from __future__ import annotations

import json
from pathlib import Path

from country_compare.pipelines.acquisition.snapshot import SourceSnapshotAcquirer


def test_local_source_snapshot_copies_manifest_paths_and_writes_audit(
    tmp_path: Path,
) -> None:
    raw_root = tmp_path / "raw"
    source_file = raw_root / "demo_metric" / "wb_demo_metric.csv"
    source_file.parent.mkdir(parents=True)
    source_file.write_text("header\nvalue\n", encoding="utf-8")

    manifest_path = tmp_path / "manifest.yaml"
    manifest_path.write_text(
        "\n".join(
            [
                "name: demo",
                f"raw_root: {raw_root.as_posix()}",
                "sources:",
                "  - source_id: wb_demo_metric",
                "    adapter_id: world_bank_indicator_csv",
                "    path: demo_metric/wb_demo_metric.csv",
                "    metric_id: demo_metric",
                "    expected_indicator_code: DEMO.INDICATOR",
            ]
        ),
        encoding="utf-8",
    )

    result = SourceSnapshotAcquirer(
        workspace_root=tmp_path / "work"
    ).acquire_manifest_sources(
        job_id="job_123",
        source_family="world_bank",
        manifest_path=manifest_path,
        acquisition_mode="local",
    )

    snapshot_file = Path(result.raw_dir) / "demo_metric" / "wb_demo_metric.csv"
    assert snapshot_file.exists()
    assert snapshot_file.read_text(encoding="utf-8") == "header\nvalue\n"
    assert result.assets[0].source_id == "wb_demo_metric"
    assert result.assets[0].metric_id == "demo_metric"
    assert result.assets[0].indicator_code == "DEMO.INDICATOR"
    assert result.assets[0].normalized_file_path == (
        "raw/demo_metric/wb_demo_metric.csv"
    )

    audit = json.loads(Path(result.audit_path).read_text(encoding="utf-8"))
    assert audit["job_id"] == "job_123"
    assert audit["source_family"] == "world_bank"
    assert audit["assets"][0]["sha256"] == result.assets[0].sha256
