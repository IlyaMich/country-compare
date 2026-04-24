from __future__ import annotations

import pandas as pd
import pytest

from country_compare.prediction import (
    PredictionDiagnosticStatus,
    PredictionMethod,
    SingleMetricPredictionRequest,
    backtest_series,
    predict_single_metric,
    predict_single_metric_for_countries,
)
from country_compare.prediction.registry import list_forecasters, resolve_forecaster


def _canonical_df(
    *,
    country_values: dict[str, list[float]] | None = None,
    years: tuple[int, ...] = (2020, 2021, 2022, 2023),
) -> pd.DataFrame:
    country_values = country_values or {
        "ISR": [10.0, 20.0, 30.0, 40.0],
        "FRA": [8.0, 12.0, 16.0, 20.0],
    }
    names = {"ISR": "Israel", "FRA": "France"}
    rows = []
    for country_code, values in country_values.items():
        for year, value in zip(years, values, strict=True):
            rows.append(
                {
                    "country_code": country_code,
                    "country_name": names.get(country_code, country_code),
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


def test_moving_average_forecast_uses_most_recent_three_observations() -> None:
    result = predict_single_metric(
        _canonical_df(country_values={"ISR": [10.0, 20.0, 30.0, 40.0]}),
        SingleMetricPredictionRequest(
            country_code="ISR",
            metric_id="gdp_per_capita",
            horizon_years=2,
            method=PredictionMethod.MOVING_AVERAGE,
        ),
    )

    assert result.diagnostics[0].status == PredictionDiagnosticStatus.OK
    assert result.diagnostics[0].method_used == "moving_average"
    assert result.forecast_df["year"].tolist() == [2024, 2025]
    assert result.forecast_df["value"].tolist() == pytest.approx([30.0, 30.0])

    info = result.forecaster_info[0]
    assert info.method_id == "moving_average"
    assert info.metadata["window_size"] == 3
    assert info.metadata["effective_window_size"] == 3
    assert info.metadata["input_years_used"] == [2021, 2022, 2023]
    assert info.metadata["moving_average_value"] == pytest.approx(30.0)


def test_moving_average_uses_all_available_when_fewer_than_window() -> None:
    result = predict_single_metric(
        _canonical_df(country_values={"ISR": [10.0, 20.0]}, years=(2022, 2023)),
        SingleMetricPredictionRequest(
            country_code="ISR",
            metric_id="gdp_per_capita",
            horizon_years=1,
            method="moving_average",
        ),
    )

    diagnostic = result.diagnostics[0]
    assert diagnostic.status == PredictionDiagnosticStatus.WARNING
    assert diagnostic.method_used == "moving_average"
    assert "fewer than 3 observations" in diagnostic.warnings[0]
    assert result.forecast_df["value"].tolist() == pytest.approx([15.0])
    assert result.forecaster_info[0].metadata["effective_window_size"] == 2
    assert result.forecaster_info[0].metadata["input_years_used"] == [2022, 2023]


def test_moving_average_falls_back_to_last_observed_for_single_observation() -> None:
    result = predict_single_metric(
        _canonical_df(country_values={"ISR": [42.0]}, years=(2023,)),
        SingleMetricPredictionRequest(
            country_code="ISR",
            metric_id="gdp_per_capita",
            horizon_years=1,
            method=PredictionMethod.MOVING_AVERAGE,
            fallback_method=PredictionMethod.LAST_OBSERVED,
        ),
    )

    diagnostic = result.diagnostics[0]
    assert diagnostic.status == PredictionDiagnosticStatus.WARNING
    assert diagnostic.method_requested == "moving_average"
    assert diagnostic.method_used == "last_observed"
    assert diagnostic.fallback_used is True
    assert result.forecast_df["value"].tolist() == pytest.approx([42.0])


def test_moving_average_is_registered_builtin_forecaster() -> None:
    assert "moving_average" in list_forecasters()
    forecaster = resolve_forecaster("moving_average")
    assert forecaster.method_id == "moving_average"


def test_batch_prediction_accepts_moving_average() -> None:
    result = predict_single_metric_for_countries(
        _canonical_df(),
        metric_id="gdp_per_capita",
        country_codes=["ISR", "FRA"],
        horizon_years=1,
        method="moving_average",
    )

    assert result.metadata["successful_series_count"] == 2
    assert result.metadata["failed_series_count"] == 0
    assert result.forecast_df["prediction_method"].unique().tolist() == ["moving_average"]
    assert result.forecast_df["value"].tolist() == pytest.approx([30.0, 16.0])


def test_backtest_series_accepts_moving_average() -> None:
    result = backtest_series(
        _canonical_df(country_values={"ISR": [10.0, 20.0, 30.0, 40.0, 50.0]}, years=(2019, 2020, 2021, 2022, 2023)),
        country_code="ISR",
        metric_id="gdp_per_capita",
        method=PredictionMethod.MOVING_AVERAGE,
        holdout_years=2,
    )

    assert result.diagnostics[0].method_used == "moving_average"
    assert result.actual_vs_predicted_df["predicted_value"].tolist() == pytest.approx([20.0, 20.0])
    assert result.metrics["mae"] == pytest.approx(25.0)