from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from tempfile import TemporaryDirectory

import pandas as pd

from country_compare.data.ingestion.registry import (
    has_source_adapter,
    list_registered_source_adapters,
)
from country_compare.pipelines import PipelineEngine, ProcessingRequest, SourceSpec
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


def _make_invalid_dataframe() -> pd.DataFrame:
    invalid = _make_valid_dataframe().copy(deep=True)
    return invalid.drop(columns=["country_code"])


def _print_section(title: str) -> None:
    print(f"\n{'=' * 80}\n{title}\n{'=' * 80}")


def main() -> None:
    _print_section("1) Check built-in adapter registration")
    print("registered adapters:", list_registered_source_adapters())
    print(
        "has canonical_tabular_passthrough:",
        has_source_adapter("canonical_tabular_passthrough"),
    )

    with TemporaryDirectory() as tmp_dir:
        root = Path(tmp_dir)
        valid_path = root / "canonical_input.csv"
        invalid_path = root / "invalid_input.csv"

        _make_valid_dataframe().to_csv(valid_path, index=False)
        _make_invalid_dataframe().to_csv(invalid_path, index=False)

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

        _print_section("3) Success path: acquire -> adapt -> validate -> publish")
        store = InMemoryStore()
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
        )
        success_result = PipelineEngine().run(success_request)
        print("result.ok:", success_result.ok)
        print("validation ok:", success_result.validation_report.ok if success_result.validation_report else None)
        print(
            "publication ok:",
            success_result.publication_report.ok if success_result.publication_report else None,
        )
        print("published rows:", 0 if store.written is None else len(store.written.index))
        if success_result.canonical_dataframe is not None:
            print(success_result.canonical_dataframe.head().to_string(index=False))

        _print_section("4) Missing source failure")
        missing_request = ProcessingRequest(
            sources=[
                SourceSpec(
                    source_id="demo_missing",
                    adapter_id="canonical_tabular_passthrough",
                    path="missing_file.csv",
                )
            ],
            raw_root=root,
        )
        missing_result = PipelineEngine().run(missing_request)
        print("result.ok:", missing_result.ok)
        print("error:", missing_result.error)
        print("warnings:", missing_result.warnings)

        _print_section("5) Canonical validation / shaping failure")
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

        _print_section("6) Phase A demo verdict")
        checks = {
            "adapter_registered": has_source_adapter("canonical_tabular_passthrough"),
            "acquisition_found_file": len(assets) == 1,
            "success_flow_ok": success_result.ok,
            "publish_flow_ok": bool(success_result.publication_report and success_result.publication_report.ok),
            "missing_source_detected": (missing_result.ok is False) and bool(missing_result.error),
            "invalid_input_detected": (invalid_result.ok is False) and bool(invalid_result.warnings or invalid_result.error),
        }
        for key, value in checks.items():
            print(f"{key}: {value}")

        overall_ok = all(checks.values())
        print("\nOVERALL_PHASE_A_DEMO:", "PASS" if overall_ok else "FAIL")
        if not overall_ok:
            raise SystemExit(1)


if __name__ == "__main__":
    main()
