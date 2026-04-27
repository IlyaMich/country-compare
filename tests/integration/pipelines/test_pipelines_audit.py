from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from country_compare.data.ingestion.base import SourceAdapter
from country_compare.data.ingestion.registry import (
    register_source_adapter,
    unregister_source_adapter,
)
from country_compare.pipelines.engine import PipelineEngine
from country_compare.pipelines.models import (
    AdapterResult,
    ProcessingRequest,
    RejectedRow,
    RowIssue,
    SourceSpec,
)


class WideLikeIssueAdapter(SourceAdapter):
    def process(self, assets, *, source_spec=None):
        dataframe = pd.DataFrame(
            {
                "country_code": ["ISR"],
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
        return AdapterResult(
            dataframe=dataframe,
            raw_row_count=2,
            issues=[
                RowIssue(
                    severity="warning",
                    code="non_numeric_value_dropped",
                    message="dropped one row with a non-numeric value",
                    source_id=getattr(source_spec, "source_id", None),
                    adapter_id=getattr(source_spec, "adapter_id", None),
                    row_identifier="row-2",
                    raw_row_number=2,
                    columns=("value",),
                    action="dropped",
                    stage="adapter",
                )
            ],
            rejected_rows=[
                RejectedRow(
                    reason="non-numeric value",
                    source_id=getattr(source_spec, "source_id", None),
                    adapter_id=getattr(source_spec, "adapter_id", None),
                    row_identifier="row-2",
                    raw_row_number=2,
                    columns=("value",),
                    payload={"Country Name": "Germany", "2023": "n/a"},
                )
            ],
            warnings=["dropped one invalid raw row during harmonization"],
        )

    def to_standardized_dataframe(
        self,
    ) -> pd.DataFrame:  # pragma: no cover - compat path only
        raise NotImplementedError


def _make_canonical_dataframe() -> pd.DataFrame:
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


def test_audit_artifacts_are_written_when_enabled(tmp_path: Path) -> None:
    csv_path = tmp_path / "canonical.csv"
    _make_canonical_dataframe().to_csv(csv_path, index=False)
    audit_dir = tmp_path / "audit"

    result = PipelineEngine().run(
        ProcessingRequest(
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
            write_audit_artifacts=True,
            output_dir=audit_dir,
        )
    )

    assert result.ok is True
    assert result.audit_report is not None and result.audit_report.written is True
    expected_keys = {
        "run_summary",
        "source_summary",
        "row_issues",
        "rejected_rows",
        "publication_summary",
        "canonical_preview",
    }
    assert expected_keys.issubset(set(result.audit_report.artifact_paths))
    for path in result.audit_report.artifact_paths.values():
        assert Path(path).exists()

    run_summary = json.loads(
        (audit_dir / "run_summary.json").read_text(encoding="utf-8")
    )
    assert run_summary["ok"] is True
    assert run_summary["run_metadata"]["successful_source_count"] == 1
    assert run_summary["row_counts"]["canonical"] == 2


def test_audit_artifacts_are_not_written_when_disabled(tmp_path: Path) -> None:
    csv_path = tmp_path / "canonical.csv"
    _make_canonical_dataframe().to_csv(csv_path, index=False)
    audit_dir = tmp_path / "audit"

    result = PipelineEngine().run(
        ProcessingRequest(
            sources=[
                SourceSpec(
                    source_id="canonical_source",
                    adapter_id="canonical_tabular_passthrough",
                    path=csv_path.name,
                )
            ],
            raw_root=tmp_path,
            output_dir=audit_dir,
        )
    )

    assert result.ok is True
    assert result.audit_report is None
    assert not audit_dir.exists()


def test_source_summary_and_issue_exports_capture_rejected_rows(tmp_path: Path) -> None:
    register_source_adapter(
        "wide_year_metric_csv_stub", WideLikeIssueAdapter, replace=True
    )
    try:
        raw_path = tmp_path / "wide_like.csv"
        pd.DataFrame(
            {"Country Name": ["Israel", "Germany"], "2023": [54000.0, "n/a"]}
        ).to_csv(
            raw_path,
            index=False,
        )
        audit_dir = tmp_path / "audit"

        result = PipelineEngine().run(
            ProcessingRequest(
                sources=[
                    SourceSpec(
                        source_id="wide_source",
                        adapter_id="wide_year_metric_csv_stub",
                        path=raw_path.name,
                    )
                ],
                raw_root=tmp_path,
                write_audit_artifacts=True,
                output_dir=audit_dir,
            )
        )

        assert result.ok is True

        source_summary = json.loads(
            (audit_dir / "source_summary.json").read_text(encoding="utf-8")
        )
        assert source_summary[0]["source_id"] == "wide_source"
        assert source_summary[0]["raw_row_count"] == 2
        assert source_summary[0]["canonical_row_count"] == 1
        assert source_summary[0]["rejected_row_count"] == 1
        assert source_summary[0]["issue_count"] == 1

        issues_df = pd.read_csv(audit_dir / "row_issues.csv")
        assert len(issues_df.index) == 1
        assert issues_df.iloc[0]["code"] == "non_numeric_value_dropped"
        assert issues_df.iloc[0]["row_identifier"] == "row-2"

        rejected_df = pd.read_csv(audit_dir / "rejected_rows.csv")
        assert len(rejected_df.index) == 1
        assert rejected_df.iloc[0]["reason"] == "non-numeric value"
        assert rejected_df.iloc[0]["row_identifier"] == "row-2"
    finally:
        unregister_source_adapter("wide_year_metric_csv_stub")


def test_partial_source_failure_is_reflected_in_audit_summary(tmp_path: Path) -> None:
    csv_path = tmp_path / "canonical.csv"
    _make_canonical_dataframe().to_csv(csv_path, index=False)
    audit_dir = tmp_path / "audit"

    result = PipelineEngine().run(
        ProcessingRequest(
            sources=[
                SourceSpec(
                    source_id="good_source",
                    adapter_id="canonical_tabular_passthrough",
                    path=csv_path.name,
                ),
                SourceSpec(
                    source_id="missing_source",
                    adapter_id="canonical_tabular_passthrough",
                    path="missing.csv",
                ),
            ],
            raw_root=tmp_path,
            write_audit_artifacts=True,
            output_dir=audit_dir,
        )
    )

    assert result.ok is True
    assert any("missing_source" in warning for warning in result.warnings)

    run_summary = json.loads(
        (audit_dir / "run_summary.json").read_text(encoding="utf-8")
    )
    assert run_summary["source_counts"]["successful"] == 1
    assert run_summary["source_counts"]["failed"] == 1

    source_summary = json.loads(
        (audit_dir / "source_summary.json").read_text(encoding="utf-8")
    )
    assert len(source_summary) == 2
    assert {item["source_id"] for item in source_summary} == {
        "good_source",
        "missing_source",
    }
    failed = next(
        item for item in source_summary if item["source_id"] == "missing_source"
    )
    assert failed["ok"] is False
    assert failed["error"]


def test_duplicate_merge_failure_writes_failure_summary(tmp_path: Path) -> None:
    dataframe = _make_canonical_dataframe()
    first = tmp_path / "first.csv"
    second = tmp_path / "second.csv"
    dataframe.to_csv(first, index=False)
    dataframe.to_csv(second, index=False)
    audit_dir = tmp_path / "audit"

    result = PipelineEngine().run(
        ProcessingRequest(
            sources=[
                SourceSpec(
                    source_id="first_source",
                    adapter_id="canonical_tabular_passthrough",
                    path=first.name,
                ),
                SourceSpec(
                    source_id="second_source",
                    adapter_id="canonical_tabular_passthrough",
                    path=second.name,
                ),
            ],
            raw_root=tmp_path,
            write_audit_artifacts=True,
            output_dir=audit_dir,
        )
    )

    assert result.ok is False
    assert result.error is not None
    assert "duplicate canonical primary-key rows" in result.error

    run_summary = json.loads(
        (audit_dir / "run_summary.json").read_text(encoding="utf-8")
    )
    assert run_summary["ok"] is False
    assert any(
        "duplicate canonical primary-key rows" in message
        for message in run_summary["validation"]["errors"]
    )
    assert "canonical_preview" not in result.audit_report.artifact_paths
