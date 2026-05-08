from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from country_compare.ui.components.prediction_quality import (
    build_prediction_limitations,
    build_prediction_quality_notice,
    build_prediction_quality_summary,
)


class DemoStatus(StrEnum):
    OK = "ok"
    WARNING = "warning"
    FAILED = "failed"


@dataclass(frozen=True)
class DemoDiagnostic:
    status: DemoStatus
    fallback_used: bool = False
    warnings: list[str] = field(default_factory=list)
    errors: list[Any] = field(default_factory=list)
    missing_years: list[int] = field(default_factory=list)


def test_build_prediction_quality_summary_good() -> None:
    summary = build_prediction_quality_summary(
        diagnostics=[
            DemoDiagnostic(status=DemoStatus.OK),
            DemoDiagnostic(status=DemoStatus.OK),
        ]
    )

    assert summary.total_series == 2
    assert summary.ok_series == 2
    assert summary.quality_label == "Good"


def test_build_prediction_quality_summary_warns_on_fallback() -> None:
    summary = build_prediction_quality_summary(
        diagnostics=[
            DemoDiagnostic(
                status=DemoStatus.WARNING,
                fallback_used=True,
                warnings=["fallback used"],
                missing_years=[2020],
            )
        ]
    )

    assert summary.warning_series == 1
    assert summary.fallback_series == 1
    assert summary.warning_count == 1
    assert summary.missing_year_count == 1
    assert summary.quality_label == "Usable with caveats"


def test_build_prediction_quality_summary_failed() -> None:
    summary = build_prediction_quality_summary(
        diagnostics=[
            DemoDiagnostic(
                status=DemoStatus.FAILED,
                errors=["failed"],
            )
        ]
    )

    assert summary.failed_series == 1
    assert summary.error_count == 1
    assert summary.quality_label == "Needs review"


def test_build_prediction_quality_summary_uses_summary_counts_without_diagnostics() -> (
    None
):
    summary = build_prediction_quality_summary(
        diagnostics=[],
        summary={
            "diagnostics": {
                "status_counts": {
                    "ok": 2,
                    "warning": 1,
                    "failed": 0,
                }
            }
        },
    )

    assert summary.total_series == 3
    assert summary.ok_series == 2
    assert summary.warning_series == 1


def test_build_prediction_limitations_adds_mode_specific_notes() -> None:
    backtest_limitations = build_prediction_limitations(mode="backtest")
    comparison_limitations = build_prediction_limitations(
        mode="predicted_single_metric_comparison"
    )

    assert any("holdout split" in item for item in backtest_limitations)
    assert any("rank forecasted values" in item for item in comparison_limitations)


def test_build_prediction_quality_notice_warns_on_failure() -> None:
    summary = build_prediction_quality_summary(
        diagnostics=[
            DemoDiagnostic(
                status=DemoStatus.FAILED,
                errors=["failed"],
            )
        ]
    )

    notice = build_prediction_quality_notice(quality=summary, mode="prediction")

    assert notice.level == "warning"
    assert "failed" in notice.message


def test_build_prediction_quality_notice_warns_on_fallback() -> None:
    summary = build_prediction_quality_summary(
        diagnostics=[
            DemoDiagnostic(
                status=DemoStatus.WARNING,
                fallback_used=True,
                warnings=["fallback used"],
            )
        ]
    )

    notice = build_prediction_quality_notice(quality=summary, mode="prediction")

    assert notice.level == "warning"
    assert "caveats" in notice.message


def test_build_prediction_quality_notice_explains_predicted_comparison() -> None:
    summary = build_prediction_quality_summary(
        diagnostics=[DemoDiagnostic(status=DemoStatus.OK)]
    )

    notice = build_prediction_quality_notice(
        quality=summary,
        mode="predicted_single_metric_comparison",
    )

    assert notice.level == "info"
    assert "rank forecasted values" in notice.message


def test_build_prediction_quality_notice_explains_backtest() -> None:
    summary = build_prediction_quality_summary(
        diagnostics=[DemoDiagnostic(status=DemoStatus.OK)]
    )

    notice = build_prediction_quality_notice(quality=summary, mode="backtest")

    assert notice.level == "info"
    assert "held-out historical years" in notice.message


def test_build_prediction_quality_notice_explains_baseline_forecast() -> None:
    summary = build_prediction_quality_summary(
        diagnostics=[DemoDiagnostic(status=DemoStatus.OK)]
    )

    notice = build_prediction_quality_notice(quality=summary, mode="single_forecast")

    assert notice.level == "info"
    assert "baseline statistical projections" in notice.message
