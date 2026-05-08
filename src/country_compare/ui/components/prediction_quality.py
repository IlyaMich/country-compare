from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Literal

import pandas as pd
import streamlit as st


@dataclass(frozen=True)
class PredictionQualitySummary:
    total_series: int
    ok_series: int
    warning_series: int
    failed_series: int
    fallback_series: int
    warning_count: int
    error_count: int
    missing_year_count: int
    quality_label: str
    quality_message: str


@dataclass(frozen=True)
class PredictionQualityNotice:
    level: Literal["info", "warning"]
    message: str


def build_prediction_quality_summary(
    *,
    diagnostics: Sequence[Any] | None = None,
    summary: Mapping[str, Any] | None = None,
) -> PredictionQualitySummary:
    diagnostics = list(diagnostics or [])
    summary = dict(summary or {})

    diagnostics_summary = dict(summary.get("diagnostics") or {})
    status_counts = dict(diagnostics_summary.get("status_counts") or {})

    total_series = len(diagnostics)
    ok_series = _status_count(diagnostics, "ok")
    warning_series = _status_count(diagnostics, "warning")
    failed_series = _status_count(diagnostics, "failed")

    if total_series == 0 and status_counts:
        ok_series = int(status_counts.get("ok") or 0)
        warning_series = int(status_counts.get("warning") or 0)
        failed_series = int(status_counts.get("failed") or 0)
        total_series = ok_series + warning_series + failed_series

    fallback_series = sum(
        1 for item in diagnostics if bool(getattr(item, "fallback_used", False))
    )
    warning_count = sum(
        len(list(getattr(item, "warnings", []) or [])) for item in diagnostics
    )
    error_count = sum(
        len(list(getattr(item, "errors", []) or [])) for item in diagnostics
    )
    missing_year_count = sum(
        len(list(getattr(item, "missing_years", []) or [])) for item in diagnostics
    )

    if failed_series > 0 or error_count > 0:
        quality_label = "Needs review"
        quality_message = "At least one requested series failed or produced errors."
    elif warning_series > 0 or fallback_series > 0 or warning_count > 0:
        quality_label = "Usable with caveats"
        quality_message = (
            "Forecasts completed, but diagnostics include warnings or fallback usage."
        )
    elif total_series > 0:
        quality_label = "Good"
        quality_message = "Forecasts completed without reported warnings."
    else:
        quality_label = "Not available"
        quality_message = "No prediction diagnostics are available for this result."

    return PredictionQualitySummary(
        total_series=total_series,
        ok_series=ok_series,
        warning_series=warning_series,
        failed_series=failed_series,
        fallback_series=fallback_series,
        warning_count=warning_count,
        error_count=error_count,
        missing_year_count=missing_year_count,
        quality_label=quality_label,
        quality_message=quality_message,
    )


def build_prediction_quality_notice(
    *,
    quality: PredictionQualitySummary,
    mode: str | None = None,
) -> PredictionQualityNotice:
    resolved_mode = str(mode or "prediction")

    if quality.failed_series > 0 or quality.error_count > 0:
        return PredictionQualityNotice(
            level="warning",
            message=(
                "Review this output before relying on it: at least one requested "
                "series failed or produced errors."
            ),
        )

    if (
        quality.warning_series > 0
        or quality.fallback_series > 0
        or quality.warning_count > 0
        or quality.missing_year_count > 0
    ):
        return PredictionQualityNotice(
            level="warning",
            message=(
                "Use this output with caveats: diagnostics include warnings, "
                "fallback usage, or sparse internal history."
            ),
        )

    if "backtest" in resolved_mode:
        return PredictionQualityNotice(
            level="info",
            message=(
                "Backtests evaluate a method against held-out historical years; "
                "they do not guarantee future accuracy."
            ),
        )

    if "comparison" in resolved_mode:
        return PredictionQualityNotice(
            level="info",
            message=(
                "Predicted comparisons rank forecasted values and inherit the "
                "uncertainty of each forecast."
            ),
        )

    return PredictionQualityNotice(
        level="info",
        message=(
            "Forecasts are baseline statistical projections, not guarantees. "
            "Review diagnostics and limitations before using the output."
        ),
    )


def build_prediction_limitations(*, mode: str | None = None) -> list[str]:
    resolved_mode = str(mode or "prediction")

    limitations = [
        "Forecasts are baseline statistical projections, not guarantees.",
        "The module extrapolates from historical metric values and does not model causal drivers.",
        "Unexpected shocks, policy changes, methodology changes, or "
        "source revisions are not predicted.",
        "Confidence intervals are not available in the current baseline output.",
        "Sparse, stale, or irregular histories should be treated with extra caution.",
    ]

    if "backtest" in resolved_mode:
        limitations.append(
            "Backtest results describe one historical holdout split and do not"
            " prove future accuracy."
        )

    if "comparison" in resolved_mode:
        limitations.append(
            "Predicted comparisons rank forecasted values and inherit the uncertainty "
            "of each forecast."
        )

    return limitations


def render_prediction_quality_panel(
    *,
    diagnostics: Sequence[Any] | None = None,
    summary: Mapping[str, Any] | None = None,
    mode: str | None = None,
) -> None:
    quality = build_prediction_quality_summary(
        diagnostics=diagnostics,
        summary=summary,
    )

    st.markdown("### Prediction quality")

    cols = st.columns(4)
    cols[0].metric("Quality", quality.quality_label)
    cols[1].metric("Series", _metric_value(quality.total_series))
    cols[2].metric("Warnings", _metric_value(quality.warning_count))
    cols[3].metric("Failed", _metric_value(quality.failed_series))

    st.caption(quality.quality_message)

    notice = build_prediction_quality_notice(quality=quality, mode=mode)
    if notice.level == "warning":
        st.warning(notice.message)
    else:
        st.info(notice.message)

    detail_df = pd.DataFrame(
        [
            {"check": "OK series", "value": quality.ok_series},
            {"check": "Warning series", "value": quality.warning_series},
            {"check": "Failed series", "value": quality.failed_series},
            {"check": "Fallback series", "value": quality.fallback_series},
            {"check": "Warning messages", "value": quality.warning_count},
            {"check": "Error messages", "value": quality.error_count},
            {"check": "Missing internal years", "value": quality.missing_year_count},
        ]
    )

    with st.expander("Quality details", expanded=False):
        st.dataframe(detail_df, use_container_width=True, hide_index=True)

    with st.expander("Prediction limitations", expanded=False):
        for limitation in build_prediction_limitations(mode=mode):
            st.write(f"- {limitation}")


def _status_count(diagnostics: Sequence[Any], expected_status: str) -> int:
    count = 0

    for item in diagnostics:
        status = getattr(item, "status", None)
        status_value = getattr(status, "value", status)
        if str(status_value).lower() == expected_status:
            count += 1

    return count


def _metric_value(value: Any) -> str:
    if value is None or value == "":
        return "—"
    return str(value)
