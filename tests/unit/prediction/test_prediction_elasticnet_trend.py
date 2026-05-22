from __future__ import annotations

import pandas as pd
import pytest

pytest.importorskip("sklearn")

from country_compare.prediction import (  # noqa: E402
    PredictionDiagnosticStatus,
    PredictionMethod,
    SingleMetricPredictionRequest,
    backtest_series,
    predict_single_metric,
)
from country_compare.prediction.registry import (
    list_forecasters,
    resolve_forecaster,
)  # noqa: E402


def _canonical_df(
    *,
    values: list[float] | None = None,
    years: tuple[int, ...] | None = None,
) -> pd.DataFrame:
    values = values or [100.0, 102.0, 105.0, 109.0, 114.0, 120.0, 127.0, 135.0, 144.0]
    years = years or tuple(range(2015, 2015 + len(values)))

    rows = []
    for year, value in zip(years, values, strict=True):
        rows.append(
            {
                "country_code": "ISR",
                "country_name": "Israel",
                "metric_id": "gdp_per_capita",
                "metric_name": "GDP per capita",
                "value": value,
                "year": year,
                "unit": "USD",
                "source_name": "Example Source",
                "source_url": "https://example.com/gdp",
                "higher_is_better": True,
                "category": "economy",
                "dataset_version": "test-v1",
                "region": "Example Region",
                "income_group": "High income",
                "notes": None,
            }
        )

    return pd.DataFrame(rows)


def test_elasticnet_trend_is_registered_when_sklearn_is_installed() -> None:
    assert "elasticnet_trend" in list_forecasters()

    forecaster = resolve_forecaster("elasticnet_trend")

    assert forecaster.method_id == "elasticnet_trend"


def test_elasticnet_trend_forecast_returns_future_points() -> None:
    result = predict_single_metric(
        _canonical_df(),
        SingleMetricPredictionRequest(
            country_code="ISR",
            metric_id="gdp_per_capita",
            horizon_years=3,
            method=PredictionMethod.ELASTICNET_TREND,
        ),
    )

    diagnostic = result.diagnostics[0]

    assert diagnostic.status == PredictionDiagnosticStatus.OK
    assert diagnostic.method_used == "elasticnet_trend"
    assert result.forecast_df["year"].tolist() == [2024, 2025, 2026]
    assert result.forecast_df["value"].notna().all()
    assert result.forecast_df["prediction_method"].unique().tolist() == [
        "elasticnet_trend"
    ]

    info = result.forecaster_info[0]
    assert info.method_id == "elasticnet_trend"
    assert info.metadata["alpha"] == pytest.approx(0.1)
    assert info.metadata["l1_ratio"] == pytest.approx(0.5)
    assert info.metadata["training_observation_count"] == 9
    assert info.metadata["feature_columns"] == ["year_offset", "year_offset_squared"]


def test_elasticnet_trend_falls_back_when_history_is_too_short() -> None:
    result = predict_single_metric(
        _canonical_df(values=[10.0, 12.0], years=(2022, 2023)),
        SingleMetricPredictionRequest(
            country_code="ISR",
            metric_id="gdp_per_capita",
            horizon_years=1,
            method=PredictionMethod.ELASTICNET_TREND,
            fallback_method=PredictionMethod.LAST_OBSERVED,
        ),
    )

    diagnostic = result.diagnostics[0]

    assert diagnostic.status == PredictionDiagnosticStatus.WARNING
    assert diagnostic.method_requested == "elasticnet_trend"
    assert diagnostic.method_used == "last_observed"
    assert diagnostic.fallback_used is True
    assert result.forecast_df["value"].tolist() == pytest.approx([12.0])


def test_backtest_series_accepts_elasticnet_trend() -> None:
    result = backtest_series(
        _canonical_df(
            values=[
                100.0,
                102.0,
                105.0,
                109.0,
                114.0,
                120.0,
                127.0,
                135.0,
                144.0,
                154.0,
                165.0,
            ],
            years=tuple(range(2013, 2024)),
        ),
        country_code="ISR",
        metric_id="gdp_per_capita",
        method=PredictionMethod.ELASTICNET_TREND,
        holdout_years=2,
    )

    assert result.diagnostics[0].method_used == "elasticnet_trend"
    assert len(result.actual_vs_predicted_df.index) == 2
    assert result.actual_vs_predicted_df["predicted_value"].notna().all()
    assert "mae" in result.metrics
