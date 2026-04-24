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


def _make_valid_canonical_dataframe() -> pd.DataFrame:
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


def _make_wide_metric_dataframe() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "Country Name": ["Israel", "Germany", "Unknownland"],
            "Country Code": ["ISR", "DEU", ""],
            "2022": [52000, "not-a-number", 1000],
            "2023": [54000, 65000, None],
        }
    )


def _print_section(title: str) -> None:
    print(f"\n{'=' * 80}\n{title}\n{'=' * 80}")


def main() -> None:
    _print_section("1) Check built-in adapter registration")
    print("registered adapters:", list_registered_source_adapters())
    print("has canonical_tabular_passthrough:", has_source_adapter("canonical_tabular_passthrough"))
    print("has wide_year_metric_csv:", has_source_adapter("wide_year_metric_csv"))

    with TemporaryDirectory() as tmp_dir:
        root = Path(tmp_dir)
        canonical_path = root / "canonical_input.csv"
        wide_path = root / "wide_metric_input.csv"

        _make_valid_canonical_dataframe().to_csv(canonical_path, index=False)
        _make_wide_metric_dataframe().to_csv(wide_path, index=False)

        _print_section("2) Demonstrate directory acquisition")
        acquirer = DirectoryRawAcquirer()
        acquisition_source = SourceSpec(
            source_id="demo_acquisition",
            adapter_id="canonical_tabular_passthrough",
            path=canonical_path.name,
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

        _print_section("3) Passthrough success path")
        store = InMemoryStore()
        success_request = ProcessingRequest(
            sources=[
                SourceSpec(
                    source_id="demo_success",
                    adapter_id="canonical_tabular_passthrough",
                    path=canonical_path.name,
                    source_name="Example Source",
                    source_url="https://example.org/gdp",
                    dataset_version="demo_v2",
                )
            ],
            raw_root=root,
            publish=True,
            store=store,
        )
        success_result = PipelineEngine().run(success_request)
        print("result.ok:", success_result.ok)
        print(
            "publication ok:",
            success_result.publication_report.ok if success_result.publication_report else None,
        )
        print("published rows:", 0 if store.written is None else len(store.written.index))

        _print_section("4) Real raw-to-canonical adapter path")
        wide_request = ProcessingRequest(
            sources=[
                SourceSpec(
                    source_id="demo_wide",
                    adapter_id="wide_year_metric_csv",
                    path=wide_path.name,
                    metric_id="gdp_per_capita",
                    metric_name="GDP per capita",
                    unit="USD",
                    category="economy",
                    higher_is_better=True,
                    source_name="Example Source",
                    source_url="https://example.org/gdp",
                    dataset_version="demo_v2",
                )
            ],
            raw_root=root,
        )
        wide_result = PipelineEngine().run(wide_request)
        print("result.ok:", wide_result.ok)
        print("validation ok:", wide_result.validation_report.ok if wide_result.validation_report else None)
        print("issue count:", len(wide_result.issues))
        for issue in wide_result.issues:
            print(
                {
                    "severity": issue.severity,
                    "code": issue.code,
                    "row_identifier": issue.row_identifier,
                    "action": issue.action,
                }
            )
        if wide_result.canonical_dataframe is not None:
            print(wide_result.canonical_dataframe.to_string(index=False))

        _print_section("5) Duplicate merge failure demo")
        duplicate_request = ProcessingRequest(
            sources=[
                SourceSpec(
                    source_id="dup_a",
                    adapter_id="wide_year_metric_csv",
                    path=wide_path.name,
                    metric_id="gdp_per_capita",
                    metric_name="GDP per capita",
                    unit="USD",
                    category="economy",
                    higher_is_better=True,
                    source_name="Example Source",
                    source_url="https://example.org/gdp",
                ),
                SourceSpec(
                    source_id="dup_b",
                    adapter_id="wide_year_metric_csv",
                    path=wide_path.name,
                    metric_id="gdp_per_capita",
                    metric_name="GDP per capita",
                    unit="USD",
                    category="economy",
                    higher_is_better=True,
                    source_name="Example Source",
                    source_url="https://example.org/gdp",
                ),
            ],
            raw_root=root,
        )
        duplicate_result = PipelineEngine().run(duplicate_request)
        print("result.ok:", duplicate_result.ok)
        print("error:", duplicate_result.error)


if __name__ == "__main__":
    main()
