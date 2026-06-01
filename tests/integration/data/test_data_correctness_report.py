from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pandas as pd
import pytest

from country_compare.data.examples import build_example_metric_dataframe

pytestmark = pytest.mark.integration


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def test_generate_data_correctness_report_writes_markdown_and_json(tmp_path) -> None:
    dataframe = build_example_metric_dataframe()
    data_path = tmp_path / "metrics.parquet"
    markdown_path = tmp_path / "data_correctness_report.md"
    json_path = tmp_path / "data_correctness_report.json"

    dataframe.to_parquet(data_path, index=False)

    result = subprocess.run(
        [
            sys.executable,
            str(_repo_root() / "scripts" / "generate_data_correctness_report.py"),
            "--data-path",
            str(data_path),
            "--output",
            str(markdown_path),
            "--json-output",
            str(json_path),
        ],
        cwd=_repo_root(),
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert markdown_path.exists()
    assert json_path.exists()

    markdown = markdown_path.read_text(encoding="utf-8")
    payload = json.loads(json_path.read_text(encoding="utf-8"))

    assert "# Data Correctness Report" in markdown
    assert payload["status"] in {"PASS", "WARN"}
    assert not any(check["status"] == "FAIL" for check in payload["checks"])


def test_generate_data_correctness_report_fails_invalid_dataset(tmp_path) -> None:
    dataframe = build_example_metric_dataframe().copy()
    dataframe.loc[dataframe.index[0], "country_code"] = None

    data_path = tmp_path / "invalid_metrics.parquet"
    markdown_path = tmp_path / "invalid_data_correctness_report.md"
    json_path = tmp_path / "invalid_data_correctness_report.json"

    dataframe.to_parquet(data_path, index=False)

    result = subprocess.run(
        [
            sys.executable,
            str(_repo_root() / "scripts" / "generate_data_correctness_report.py"),
            "--data-path",
            str(data_path),
            "--output",
            str(markdown_path),
            "--json-output",
            str(json_path),
        ],
        cwd=_repo_root(),
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 1
    assert markdown_path.exists()
    assert json_path.exists()

    payload = json.loads(json_path.read_text(encoding="utf-8"))

    assert payload["status"] == "FAIL"
    assert any(check["status"] == "FAIL" for check in payload["checks"])


def test_generate_data_correctness_report_can_fail_on_warning(tmp_path) -> None:
    dataframe = pd.DataFrame(
        [
            {
                "country_code": "ISR",
                "country_name": "Israel",
                "metric_id": "synthetic_metric",
                "metric_name": "Synthetic Metric",
                "value": 1.0,
                "year": 2024,
                "unit": "index",
                "source_name": "Test",
                "source_url": "https://example.org",
                "higher_is_better": True,
                "category": "test",
            },
            {
                "country_code": "ISR",
                "country_name": "Israel",
                "metric_id": "synthetic_metric",
                "metric_name": "Synthetic Metric",
                "value": 10.0,
                "year": 2025,
                "unit": "index",
                "source_name": "Test",
                "source_url": "https://example.org",
                "higher_is_better": True,
                "category": "test",
            },
        ]
    )

    data_path = tmp_path / "warning_metrics.parquet"
    markdown_path = tmp_path / "warning_report.md"
    json_path = tmp_path / "warning_report.json"
    trend_rules_path = tmp_path / "trend_rules.yaml"

    dataframe.to_parquet(data_path, index=False)

    trend_rules_path.write_text(
        """
defaults:
  enabled: true
  require_consecutive_years: true
  absolute_threshold: null
  relative_threshold: null
  relative_min_previous_abs: 1.0

metrics:
  synthetic_metric:
    relative_threshold: 0.5
    relative_min_previous_abs: 0.1

reviewed_anomalies: []
""".strip(),
        encoding="utf-8",
    )

    result = subprocess.run(
        [
            sys.executable,
            str(_repo_root() / "scripts" / "generate_data_correctness_report.py"),
            "--data-path",
            str(data_path),
            "--output",
            str(markdown_path),
            "--json-output",
            str(json_path),
            "--trend-rules-path",
            str(trend_rules_path),
            "--fail-on-warning",
        ],
        cwd=_repo_root(),
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 1
    assert markdown_path.exists()
    assert json_path.exists()
    assert "status WARN" in result.stdout
