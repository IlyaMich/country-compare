from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from tempfile import TemporaryDirectory

import pandas as pd
import yaml

from country_compare.data.ingestion.registry import (
    has_source_adapter,
    list_registered_source_adapters,
)
from country_compare.pipelines import SourceSpec
from country_compare.pipelines.acquisition.directory import DirectoryRawAcquirer
from country_compare.pipelines.runners import run_processing_manifest


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


def _write_manifest(path: Path, payload: dict) -> None:
    path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")


def _print_section(title: str) -> None:
    print(f"\n{'=' * 80}\n{title}\n{'=' * 80}")


def main() -> None:
    _print_section("1) Check built-in adapter registration")
    print("registered adapters:", list_registered_source_adapters())
    print(
        "has canonical_tabular_passthrough:",
        has_source_adapter("canonical_tabular_passthrough"),
    )
    print("has wide_year_metric_csv:", has_source_adapter("wide_year_metric_csv"))

    with TemporaryDirectory() as tmp_dir:
        root = Path(tmp_dir)
        valid_path = root / "canonical_input.csv"
        duplicate_a_path = root / "duplicate_a.csv"
        duplicate_b_path = root / "duplicate_b.csv"
        audit_dir = root / "audit_output"
        manifest_success_path = root / "manifest_success.yaml"
        manifest_conflict_path = root / "manifest_conflict.yaml"

        valid_df = _make_valid_dataframe()
        valid_df.to_csv(valid_path, index=False)
        valid_df.iloc[[0]].to_csv(duplicate_a_path, index=False)
        valid_df.iloc[[0]].to_csv(duplicate_b_path, index=False)

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

        _write_manifest(
            manifest_success_path,
            {
                "name": "demo_success_manifest",
                "raw_root": str(root),
                "tags": ["demo", "batch"],
                "labels": {"owner": "demo"},
                "processing": {
                    "publish": True,
                    "write_audit_artifacts": True,
                    "output_dir": str(audit_dir),
                    "canonical_preview_rows": 2,
                },
                "defaults": {
                    "adapter_id": "canonical_tabular_passthrough",
                    "source_name": "Example Source",
                    "source_url": "https://example.org/gdp",
                    "dataset_version": "demo_v2",
                },
                "sources": [
                    {
                        "source_id": "demo_success",
                        "path": valid_path.name,
                    }
                ],
            },
        )

        _write_manifest(
            manifest_conflict_path,
            {
                "name": "demo_conflict_manifest",
                "raw_root": str(root),
                "processing": {
                    "publish": False,
                },
                "defaults": {
                    "adapter_id": "canonical_tabular_passthrough",
                    "source_name": "Example Source",
                    "source_url": "https://example.org/gdp",
                },
                "sources": [
                    {"source_id": "duplicate_a", "path": duplicate_a_path.name},
                    {"source_id": "duplicate_b", "path": duplicate_b_path.name},
                ],
            },
        )

        _print_section("3) Manifest-driven success path")
        store = InMemoryStore()
        success_result = run_processing_manifest(manifest_success_path, store=store)
        print("result.ok:", success_result.ok)
        print(
            "merge ok:",
            success_result.merge_report.ok if success_result.merge_report else None,
        )
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
            "audit written:",
            (
                success_result.audit_report.written
                if success_result.audit_report
                else None
            ),
        )
        print(
            "published rows:", 0 if store.written is None else len(store.written.index)
        )
        if success_result.source_results:
            print("source tags:", success_result.source_results[0].tags)
            print("source labels:", success_result.source_results[0].labels)

        _print_section("4) Manifest-driven duplicate merge conflict reporting")
        conflict_result = run_processing_manifest(manifest_conflict_path)
        print("result.ok:", conflict_result.ok)
        print(
            "merge ok:",
            conflict_result.merge_report.ok if conflict_result.merge_report else None,
        )
        print(
            "duplicate conflicts:",
            (
                conflict_result.merge_report.duplicate_key_conflict_count
                if conflict_result.merge_report
                else None
            ),
        )
        print("error:", conflict_result.error)
        print("warnings:", conflict_result.warnings)

        _print_section("5) Phase demo verdict")
        checks = {
            "adapters_registered": has_source_adapter("canonical_tabular_passthrough")
            and has_source_adapter("wide_year_metric_csv"),
            "acquisition_found_file": len(assets) == 1,
            "manifest_success_ok": success_result.ok,
            "audit_written": bool(
                success_result.audit_report and success_result.audit_report.written
            ),
            "manifest_tags_propagated": bool(
                success_result.source_results
                and success_result.source_results[0].tags == ("demo", "batch")
            ),
            "merge_conflict_detected": bool(
                conflict_result.merge_report
                and conflict_result.merge_report.duplicate_key_conflict_count == 1
            ),
        }
        for key, value in checks.items():
            print(f"{key}: {value}")

        overall_ok = all(checks.values())
        print("\nOVERALL_PHASE_DEMO:", "PASS" if overall_ok else "FAIL")
        if not overall_ok:
            raise SystemExit(1)


if __name__ == "__main__":
    main()
