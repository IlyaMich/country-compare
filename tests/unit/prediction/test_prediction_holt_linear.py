from __future__ import annotations

import pandas as pd
import pytest

from country_compare.prediction import (
    PredictionDiagnosticStatus,
    PredictionMethod,
    SingleMetricPredictionRequest,
    backtest_series,
    predict_single_metric,
)
from country_compare.prediction.registry import list_forecasters, resolve_forecaster


def _canonical_df(
    *,
    years: tuple[int, ...] = (2020, 2021, 2022, 2023),
    values: tuple[float, ...] = (10.0, 20.0, 30.0, 40.0),
) -> pd.DataFrame:
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
                "region": "Middle East & North Africa",
                "income_group": "High income",
                "notes": None,
            }
        )
    return pd.DataFrame(rows)


def test_holt_linear_forecast_returns_expected_damped_points() -> None:
    result = predict_single_metric(
        _canonical_df(),
        SingleMetricPredictionRequest(
            country_code="ISR",
            metric_id="gdp_per_capita",
            horizon_years=2,
            method=PredictionMethod.HOLT_LINEAR,
        ),
    )

    assert result.diagnostics[0].status == PredictionDiagnosticStatus.OK
    assert result.diagnostics[0].method_used == "holt_linear"
    assert result.forecast_df["year"].tolist() == [2024, 2025]
    assert result.forecast_df["value"].tolist() == pytest.approx(
        [46.780501184, 53.3671407296]
    )

    info = result.forecaster_info[0]
    assert info.method_id == "holt_linear"
    assert info.metadata["alpha"] == pytest.approx(0.8)
    assert info.metadata["beta"] == pytest.approx(0.2)
    assert info.metadata["damped"] is True
    assert info.metadata["phi"] == pytest.approx(0.9)
    assert info.metadata["training_observation_count"] == 4
    assert info.metadata["training_year_min"] == 2020
    assert info.metadata["training_year_max"] == 2023
    assert "final_level" in info.metadata
    assert "final_trend" in info.metadata


def test_holt_linear_falls_back_when_history_is_too_short() -> None:
    result = predict_single_metric(
        _canonical_df(years=(2021, 2022, 2023), values=(10.0, 20.0, 30.0)),
        SingleMetricPredictionRequest(
            country_code="ISR",
            metric_id="gdp_per_capita",
            horizon_years=1,
            method=PredictionMethod.HOLT_LINEAR,
            fallback_method=PredictionMethod.LAST_OBSERVED,
        ),
    )

    diagnostic = result.diagnostics[0]
    assert diagnostic.status == PredictionDiagnosticStatus.WARNING
    assert diagnostic.method_requested == "holt_linear"
    assert diagnostic.method_used == "last_observed"
    assert diagnostic.fallback_used is True
    assert result.forecast_df["value"].tolist() == pytest.approx([30.0])


def test_holt_linear_is_registered_builtin_forecaster() -> None:
    assert "holt_linear" in list_forecasters()

    forecaster = resolve_forecaster("holt_linear")
    assert forecaster.method_id == "holt_linear"


def test_backtest_series_accepts_holt_linear() -> None:
    result = backtest_series(
        _canonical_df(
            years=(2018, 2019, 2020, 2021, 2022, 2023),
            values=(10.0, 20.0, 30.0, 40.0, 50.0, 60.0),
        ),
        country_code="ISR",
        metric_id="gdp_per_capita",
        method=PredictionMethod.HOLT_LINEAR,
        holdout_years=2,
    )

    assert result.diagnostics[0].method_used == "holt_linear"
    assert result.metrics["method_used"] == "holt_linear"
    assert result.metrics["fallback_used"] is False
    assert result.actual_vs_predicted_df["year"].tolist() == [2022, 2023]
