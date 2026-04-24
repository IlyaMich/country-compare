from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def test_demo_product_flow_runs_successfully(tmp_path: Path) -> None:
    result = subprocess.run(
        [
            sys.executable,
            "scripts/demo_flow.py",
            "--output-dir",
            str(tmp_path),
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    assert "Golden demo completed successfully." in result.stdout

    expected_outputs = {
        "single_metric_comparison.csv",
        "multi_metric_comparison.csv",
        "weighted_score.csv",
        "forecast_table.csv",
        "predicted_single_metric_comparison.csv",
    }

    for filename in expected_outputs:
        assert (tmp_path / filename).exists()
