from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from tempfile import TemporaryDirectory

import pandas as pd

from country_compare.data.ingestion.base import SourceAdapter
from country_compare.data.ingestion.registry import (
    has_source_adapter,
    list_registered_source_adapters,
    register_source_adapter,
    unregister_source_adapter,
)
from country_compare.pipelines import PipelineEngine, ProcessingRequest, SourceSpec
from country_compare.pipelines.acquisition.directory import DirectoryRawAcquirer
from country_compare.pipelines.models import AdapterResult, RejectedRow, RowIssue


@dataclass
class InMemoryStore:
    backend_name: str = "memory"
    path: str | None = None
    written: pd.DataFrame | None = None

    def read(self, columns: list[str] | None = None) -> pd.DataFrame:
        if self.written is None:
            return pd.DataFrame()
        if columns is None:
            return self.written.copy(deep=True)
        return self.written.loc[:, columns].copy(deep=True)

    def write(self, dataframe: pd.DataFrame) -> None:
        self.written = dataframe.copy(deep=True)

    def exists(self) -> bool:
        return self.written is not None

    def delete(self) -> None:
        self.written = None


class DemoIssueAdapter(SourceAdapter):
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


def _make_valid_dataframe() -> pd.DataFrame:
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


def _make_invalid_dataframe() -> pd.DataFrame:
    invalid = _make_valid_dataframe().copy(deep=True)
    return invalid.drop(columns=["country_code"])


def _print_section(title: str) -> None:
    print(f"\n{'=' * 80}\n{title}\n{'=' * 80}")


def _print_audit_paths(result) -> None:
    audit_report = getattr(result, "audit_report", None)
    if audit_report is None:
        print("audit written:", False)
        return
    print("audit written:", audit_report.written)
    print("audit output dir:", audit_report.output_dir)
    for key, value in sorted(audit_report.artifact_paths.items()):
        print(f"  {key}: {value}")


def main() -> None:
    _print_section("1) Check built-in adapter registration")
    print("registered adapters:", list_registered_source_adapters())
    print(
        "has canonical_tabular_passthrough:",
        has_source_adapter("canonical_tabular_passthrough"),
    )

    register_source_adapter("demo_issue_adapter", DemoIssueAdapter, replace=True)

    with TemporaryDirectory() as tmp_dir:
        root = Path(tmp_dir)
        valid_path = root / "canonical_input.csv"
        invalid_path = root / "invalid_input.csv"
        issue_raw_path = root / "issue_input.csv"

        _make_valid_dataframe().to_csv(valid_path, index=False)
        _make_invalid_dataframe().to_csv(invalid_path, index=False)
        pd.DataFrame(
            {"Country Name": ["Israel", "Germany"], "2023": [54000.0, "n/a"]}
        ).to_csv(
            issue_raw_path,
            index=False,
        )

        _print_section("2) Demonstrate directory acquisition")
        acquirer = DirectoryRawAcquirer()
        acquisition_source = SourceSpec(
            source_id="demo_acquisition",
            adapter_id="canonical_tabular_passthrough",
            path=valid_path.name,
        )
        assets = acquirer.acquire(acquisition_source, raw_root=root)
        for asset in assets:
            print(
                {
                    "source_id": asset.source_id,
                    "adapter_id": asset.adapter_id,
                    "path": str(asset.local_path),
                    "format": asset.file_format,
                    "size": asset.file_size,
                    "checksum": asset.checksum[:12] if asset.checksum else None,
                }
            )

        _print_section("3) Success path with publication + audit artifacts")
        store = InMemoryStore()
        success_audit_dir = root / "audit_success"
        success_request = ProcessingRequest(
            sources=[
                SourceSpec(
                    source_id="demo_success",
                    adapter_id="canonical_tabular_passthrough",
                    path=valid_path.name,
                    source_name="Example Source",
                    source_url="https://example.org/gdp",
                    dataset_version="demo_v1",
                )
            ],
            raw_root=root,
            publish=True,
            store=store,
            write_audit_artifacts=True,
            output_dir=success_audit_dir,
        )
        success_result = PipelineEngine().run(success_request)
        print("result.ok:", success_result.ok)
        print(
            "validation ok:",
            (
                success_result.validation_report.ok
                if success_result.validation_report
                else None
            ),
        )
        print(
            "publication ok:",
            (
                success_result.publication_report.ok
                if success_result.publication_report
                else None
            ),
        )
        print(
            "published rows:", 0 if store.written is None else len(store.written.index)
        )
        _print_audit_paths(success_result)

        _print_section("4) Issue/rejected-row audit export")
        issue_audit_dir = root / "audit_issue"
        issue_request = ProcessingRequest(
            sources=[
                SourceSpec(
                    source_id="demo_issue_source",
                    adapter_id="demo_issue_adapter",
                    path=issue_raw_path.name,
                )
            ],
            raw_root=root,
            write_audit_artifacts=True,
            output_dir=issue_audit_dir,
        )
        issue_result = PipelineEngine().run(issue_request)
        print("result.ok:", issue_result.ok)
        if issue_result.audit_report is not None:
            issues_df = pd.read_csv(issue_audit_dir / "row_issues.csv")
            rejected_df = pd.read_csv(issue_audit_dir / "rejected_rows.csv")
            print("issue rows exported:", len(issues_df.index))
            print("rejected rows exported:", len(rejected_df.index))
            print("source summary:")
            print(
                json.dumps(
                    json.loads(
                        (issue_audit_dir / "source_summary.json").read_text(
                            encoding="utf-8"
                        )
                    ),
                    indent=2,
                )
            )

        _print_section("5) Duplicate merge failure with audit")
        duplicate_audit_dir = root / "audit_duplicate"
        duplicate_request = ProcessingRequest(
            sources=[
                SourceSpec(
                    source_id="duplicate_a",
                    adapter_id="canonical_tabular_passthrough",
                    path=valid_path.name,
                ),
                SourceSpec(
                    source_id="duplicate_b",
                    adapter_id="canonical_tabular_passthrough",
                    path=valid_path.name,
                ),
            ],
            raw_root=root,
            write_audit_artifacts=True,
            output_dir=duplicate_audit_dir,
        )
        duplicate_result = PipelineEngine().run(duplicate_request)
        print("result.ok:", duplicate_result.ok)
        print("error:", duplicate_result.error)
        _print_audit_paths(duplicate_result)

        _print_section("6) Canonical validation / shaping failure")
        invalid_request = ProcessingRequest(
            sources=[
                SourceSpec(
                    source_id="demo_invalid",
                    adapter_id="canonical_tabular_passthrough",
                    path=invalid_path.name,
                )
            ],
            raw_root=root,
        )
        invalid_result = PipelineEngine().run(invalid_request)
        print("result.ok:", invalid_result.ok)
        print("error:", invalid_result.error)
        print("warnings:", invalid_result.warnings)
        if invalid_result.source_results:
            print("source error:", invalid_result.source_results[0].error)

        _print_section("7) Phase C demo verdict")
        checks = {
            "adapter_registered": has_source_adapter("canonical_tabular_passthrough"),
            "acquisition_found_file": len(assets) == 1,
            "success_flow_ok": success_result.ok,
            "publish_flow_ok": bool(
                success_result.publication_report
                and success_result.publication_report.ok
            ),
            "success_audit_written": bool(
                success_result.audit_report and success_result.audit_report.written
            ),
            "issue_export_written": bool(
                issue_result.audit_report and issue_result.audit_report.written
            ),
            "duplicate_detected": (duplicate_result.ok is False)
            and bool(duplicate_result.error),
            "invalid_input_detected": (invalid_result.ok is False)
            and bool(invalid_result.warnings or invalid_result.error),
        }
        for key, value in checks.items():
            print(f"{key}: {value}")

        overall_ok = all(checks.values())
        print("\nOVERALL_PHASE_C_DEMO:", "PASS" if overall_ok else "FAIL")
        if not overall_ok:
            raise SystemExit(1)

    unregister_source_adapter("demo_issue_adapter")


if __name__ == "__main__":
    main()
