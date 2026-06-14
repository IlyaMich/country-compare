from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pandas as pd


@dataclass(frozen=True, slots=True)
class DatasetSummary:
    row_count: int
    country_count: int
    metric_count: int
    year_min: int | None
    year_max: int | None

    def as_dict(self) -> dict[str, int | None]:
        return {
            "row_count": self.row_count,
            "country_count": self.country_count,
            "metric_count": self.metric_count,
            "year_min": self.year_min,
            "year_max": self.year_max,
        }


@dataclass(frozen=True, slots=True)
class DatasetDiffReport:
    summary: DatasetSummary
    no_changes: bool = False
    compared_to_uri: str | None = None
    notes: tuple[str, ...] = ()

    def as_dict(self) -> dict[str, Any]:
        return {
            "summary": self.summary.as_dict(),
            "no_changes": self.no_changes,
            "compared_to_uri": self.compared_to_uri,
            "notes": list(self.notes),
        }

    def as_markdown(self) -> str:
        summary = self.summary
        lines = [
            "# Dataset Diff Report",
            "",
            "Milestone 1 generates a structural summary only. Full baseline comparison "
            "is added with the dataset registry in a later milestone.",
            "",
            "| Field | Value |",
            "|---|---:|",
            f"| Rows | {summary.row_count} |",
            f"| Countries | {summary.country_count} |",
            f"| Metrics | {summary.metric_count} |",
            f"| Year min | {summary.year_min if summary.year_min is not None else 'n/a'} |",
            f"| Year max | {summary.year_max if summary.year_max is not None else 'n/a'} |",
            "",
            f"No changes detected: `{str(self.no_changes).lower()}`",
        ]
        if self.notes:
            lines.extend(["", "## Notes"])
            lines.extend(f"- {note}" for note in self.notes)
        return "\n".join(lines) + "\n"


def summarize_dataframe(dataframe: pd.DataFrame) -> DatasetSummary:
    years = (
        pd.to_numeric(dataframe.get("year"), errors="coerce")
        if "year" in dataframe
        else None
    )
    valid_years = years.dropna() if years is not None else pd.Series(dtype="float64")
    return DatasetSummary(
        row_count=int(len(dataframe.index)),
        country_count=(
            int(dataframe["country_code"].nunique())
            if "country_code" in dataframe
            else 0
        ),
        metric_count=(
            int(dataframe["metric_id"].nunique()) if "metric_id" in dataframe else 0
        ),
        year_min=(int(valid_years.min()) if not valid_years.empty else None),
        year_max=(int(valid_years.max()) if not valid_years.empty else None),
    )


def generate_diff_report(dataframe: pd.DataFrame) -> DatasetDiffReport:
    return DatasetDiffReport(
        summary=summarize_dataframe(dataframe),
        no_changes=False,
        notes=("No previous dataset registry baseline was available in Milestone 1.",),
    )
