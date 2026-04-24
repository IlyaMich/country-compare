from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from tempfile import TemporaryDirectory

import pandas as pd

from country_compare.data.ingestion.registry import (
    has_source_adapter,
    list_registered_source_adapters,
)
from country_compare.pipelines import (
    PipelineEngine,
    SourceManifest,
    SourceSpec,
    manifest_to_processing_request,
)
from country_compare.pipelines.acquisition.directory import DirectoryRawAcquirer


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
        first_path = root / "canonical_a.csv"
        second_path = root / "canonical_b.csv"
        _make_valid_dataframe().to_csv(first_path, index=False)
        _make_valid_dataframe().to_csv(second_path, index=False)
        _print_section("2) Demonstrate directory acquisition")
        asset = DirectoryRawAcquirer().acquire(
            SourceSpec(
                source_id="demo_acquisition",
                adapter_id="canonical_tabular_passthrough",
                path=first_path.name,
            ),
            raw_root=root,
        )[0]
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
        _print_section("3) Manifest-style success path")
        store = InMemoryStore()
        success_result = PipelineEngine().run(
            manifest_to_processing_request(
                SourceManifest(
                    name="demo_manifest",
                    raw_root=root,
                    processing={
                        "publish": True,
                        "store": store,
                        "write_audit_artifacts": True,
                        "output_dir": root / "audit_success",
                    },
                    sources=[
                        SourceSpec(
                            source_id="demo_success",
                            adapter_id="canonical_tabular_passthrough",
                            path=first_path.name,
                            source_name="Example Source",
                            source_url="https://example.org/gdp",
                            tags=("manifest",),
                        )
                    ],
                )
            )
        )
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
        _print_section("4) Duplicate merge conflict reporting")
        conflict_result = PipelineEngine().run(
            manifest_to_processing_request(
                SourceManifest(
                    raw_root=root,
                    processing={
                        "write_audit_artifacts": True,
                        "output_dir": root / "audit_conflict",
                    },
                    sources=[
                        SourceSpec(
                            source_id="source_a",
                            adapter_id="canonical_tabular_passthrough",
                            path=first_path.name,
                        ),
                        SourceSpec(
                            source_id="source_b",
                            adapter_id="canonical_tabular_passthrough",
                            path=second_path.name,
                        ),
                    ],
                )
            )
        )
        print("result.ok:", conflict_result.ok)
        print("error:", conflict_result.error)
        print(
            "merge conflict count:",
            (
                conflict_result.merge_report.duplicate_key_conflict_count
                if conflict_result.merge_report
                else None
            ),
        )
        print(
            "conflict preview:",
            (
                conflict_result.merge_report.conflict_keys_preview
                if conflict_result.merge_report
                else None
            ),
        )
        print(
            "audit paths:",
            (
                conflict_result.audit_report.artifact_paths
                if conflict_result.audit_report
                else None
            ),
        )


if __name__ == "__main__":
    main()
