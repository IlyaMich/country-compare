from __future__ import annotations

import pandas as pd
import pytest

from country_compare.prediction import (
    PredictionDiagnosticStatus,
    PredictionErrorCode,
    PredictionException,
    PredictionMethod,
    backtest_series,
)


def _canonical_df(years=(2018, 2019, 2020, 2021, 2022), values=(10.0, 15.0, 20.0, 25.0, 30.0)) -> pd.DataFrame:
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


def test_backtest_series_successful_linear_trend_holdout() -> None:
    result = backtest_series(
        _canonical_df(),
        country_code="ISR",
        metric_id="gdp_per_capita",
        method=PredictionMethod.LINEAR_TREND,
        holdout_years=2,
    )

    assert result.diagnostics[0].status == PredictionDiagnosticStatus.OK
    assert result.metrics["method_requested"] == "linear_trend"
    assert result.metrics["method_used"] == "linear_trend"
    assert result.metrics["fallback_used"] is False
    assert result.metrics["n_train_observations"] == 3
    assert result.metrics["n_test_observations"] == 2
    assert result.metrics["train_start_year"] == 2018
    assert result.metrics["train_end_year"] == 2020
    assert result.metrics["test_start_year"] == 2021
    assert result.metrics["test_end_year"] == 2022
    assert result.actual_vs_predicted_df["year"].tolist() == [2021, 2022]
    assert result.actual_vs_predicted_df["actual_value"].tolist() == pytest.approx([25.0, 30.0])
    assert result.actual_vs_predicted_df["predicted_value"].tolist() == pytest.approx([25.0, 30.0])
    assert result.actual_vs_predicted_df["error"].tolist() == pytest.approx([0.0, 0.0])
    assert result.metrics["mae"] == pytest.approx(0.0)
    assert result.metrics["rmse"] == pytest.approx(0.0)
    assert result.metrics["mape"] == pytest.approx(0.0)


def test_backtest_series_invalid_holdout_size() -> None:
    with pytest.raises(PredictionException) as exc_info:
        backtest_series(
            _canonical_df(),
            country_code="ISR",
            metric_id="gdp_per_capita",
            holdout_years=0,
        )

    assert exc_info.value.code == PredictionErrorCode.INVALID_HORIZON


def test_backtest_series_requires_training_observations_before_holdout() -> None:
    with pytest.raises(PredictionException) as exc_info:
        backtest_series(
            _canonical_df(years=(2021, 2022), values=(10.0, 20.0)),
            country_code="ISR",
            metric_id="gdp_per_capita",
            holdout_years=2,
        )

    assert exc_info.value.code == PredictionErrorCode.INSUFFICIENT_HISTORY


def test_backtest_series_zero_actual_mape_handling() -> None:
    result = backtest_series(
        _canonical_df(
            years=(2018, 2019, 2020, 2021, 2022),
            values=(10.0, 15.0, 20.0, 0.0, 30.0),
        ),
        country_code="ISR",
        metric_id="gdp_per_capita",
        method=PredictionMethod.LINEAR_TREND,
        holdout_years=2,
    )

    assert result.metrics["mape"] is None
    ape = result.actual_vs_predicted_df["absolute_percentage_error"].tolist()
    assert pd.isna(ape[0])
    assert ape[1] == pytest.approx(abs(30.0 - 30.0) / 30.0)


def test_backtest_series_fallback_from_linear_trend_to_last_observed() -> None:
    result = backtest_series(
        _canonical_df(years=(2019, 2020, 2021, 2022), values=(10.0, 20.0, 25.0, 25.0)),
        country_code="ISR",
        metric_id="gdp_per_capita",
        method=PredictionMethod.LINEAR_TREND,
        fallback_method=PredictionMethod.LAST_OBSERVED,
        holdout_years=2,
    )

    diagnostic = result.diagnostics[0]
    assert diagnostic.status == PredictionDiagnosticStatus.WARNING
    assert diagnostic.method_requested == "linear_trend"
    assert diagnostic.method_used == "last_observed"
    assert diagnostic.fallback_used is True
    assert result.metrics["method_used"] == "last_observed"
    assert result.metrics["fallback_used"] is True
    assert result.actual_vs_predicted_df["predicted_value"].tolist() == pytest.approx([20.0, 20.0])


def test_backtest_series_does_not_mutate_original_dataframe() -> None:
    dataframe = _canonical_df()
    original = dataframe.copy(deep=True)

    backtest_series(
        dataframe,
        country_code="ISR",
        metric_id="gdp_per_capita",
        holdout_years=2,
    )

    pd.testing.assert_frame_equal(dataframe, original)
