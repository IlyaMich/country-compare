from __future__ import annotations

import pandas as pd
import pytest

from country_compare.comparison.single_metric import compare_metric
from country_compare.config.models import YearStrategy
from country_compare.data.contract import REQUIRED_COLUMNS
from country_compare.prediction import (
    PredictionDiagnosticStatus,
    PredictionErrorCode,
    PredictionException,
    PredictionMethod,
    SingleMetricPredictionRequest,
    predict_single_metric,
)
from country_compare.prediction.output import PREDICTION_METADATA_COLUMNS


def _canonical_df(years=(2020, 2021, 2022), values=(10.0, 15.0, 20.0)) -> pd.DataFrame:
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


def _request(**overrides) -> SingleMetricPredictionRequest:
    payload = {
        "country_code": "ISR",
        "metric_id": "gdp_per_capita",
        "horizon_years": 2,
    }
    payload.update(overrides)
    return SingleMetricPredictionRequest(**payload)


def test_successful_linear_trend_forecast() -> None:
    result = predict_single_metric(
        _canonical_df(), _request(method=PredictionMethod.LINEAR_TREND)
    )

    assert result.diagnostics[0].status == PredictionDiagnosticStatus.OK
    assert result.diagnostics[0].method_used == "linear_trend"
    assert result.forecast_df["year"].tolist() == [2023, 2024]
    assert result.forecast_df["forecast_horizon"].tolist() == [1, 2]
    assert result.forecast_df["value"].tolist() == pytest.approx([25.0, 30.0])
    assert result.combined_df["row_type"].tolist() == [
        "actual",
        "actual",
        "actual",
        "predicted",
        "predicted",
    ]


def test_successful_last_observed_forecast() -> None:
    result = predict_single_metric(
        _canonical_df(),
        _request(method=PredictionMethod.LAST_OBSERVED),
    )

    assert result.diagnostics[0].status == PredictionDiagnosticStatus.OK
    assert result.diagnostics[0].method_used == "last_observed"
    assert result.forecast_df["value"].tolist() == pytest.approx([20.0, 20.0])


def test_fallback_from_linear_trend_to_last_observed_when_history_too_short() -> None:
    result = predict_single_metric(
        _canonical_df(years=(2021, 2022), values=(10.0, 20.0)),
        _request(method=PredictionMethod.LINEAR_TREND),
    )

    diagnostic = result.diagnostics[0]
    assert diagnostic.status == PredictionDiagnosticStatus.WARNING
    assert diagnostic.method_requested == "linear_trend"
    assert diagnostic.method_used == "last_observed"
    assert diagnostic.fallback_used is True
    assert result.forecast_df["value"].tolist() == pytest.approx([20.0, 20.0])


def test_invalid_horizon() -> None:
    with pytest.raises(PredictionException) as exc_info:
        predict_single_metric(_canonical_df(), _request(horizon_years=0))

    assert exc_info.value.code == PredictionErrorCode.INVALID_HORIZON


def test_missing_country() -> None:
    with pytest.raises(PredictionException) as exc_info:
        predict_single_metric(_canonical_df(), _request(country_code="FRA"))

    assert exc_info.value.code == PredictionErrorCode.MISSING_COUNTRY


def test_missing_metric() -> None:
    with pytest.raises(PredictionException) as exc_info:
        predict_single_metric(_canonical_df(), _request(metric_id="unemployment_pct"))

    assert exc_info.value.code == PredictionErrorCode.MISSING_METRIC


def test_duplicate_year_rows() -> None:
    dataframe = pd.concat(
        [_canonical_df(), _canonical_df(years=(2021,), values=(16.0,))],
        ignore_index=True,
    )

    with pytest.raises(PredictionException) as exc_info:
        predict_single_metric(dataframe, _request())

    assert exc_info.value.code == PredictionErrorCode.DUPLICATE_SERIES_YEAR
    assert exc_info.value.details["duplicate_years"] == [2021]


def test_sparse_missing_year_warning() -> None:
    result = predict_single_metric(
        _canonical_df(years=(2020, 2022, 2023), values=(10.0, 20.0, 25.0)),
        _request(horizon_years=1),
    )

    diagnostic = result.diagnostics[0]
    assert diagnostic.status == PredictionDiagnosticStatus.WARNING
    assert diagnostic.missing_years == [2021]
    assert "missing internal years" in diagnostic.warnings[0]


def test_output_columns_include_canonical_required_columns_plus_prediction_metadata() -> (
    None
):
    result = predict_single_metric(_canonical_df(), _request(horizon_years=1))

    for column in REQUIRED_COLUMNS:
        assert column in result.forecast_df.columns
    for column in PREDICTION_METADATA_COLUMNS:
        assert column in result.forecast_df.columns

    assert result.forecast_df["row_type"].tolist() == ["predicted"]
    assert result.forecast_df["is_predicted"].tolist() == [True]
    assert result.forecast_df["prediction_run_id"].notna().all()
    assert result.forecast_df["prediction_created_at"].notna().all()
    assert result.forecast_df["confidence_lower"].isna().all()
    assert result.forecast_df["confidence_upper"].isna().all()


def test_comparison_ready_output_preserves_canonical_like_shape() -> None:
    result = predict_single_metric(_canonical_df(), _request(horizon_years=2))
    comparison_ready = result.comparison_ready_df

    assert set(REQUIRED_COLUMNS).issubset(comparison_ready.columns)
    assert (
        comparison_ready.duplicated(subset=["country_code", "metric_id", "year"]).sum()
        == 0
    )
    assert comparison_ready["row_type"].eq("predicted").all()

    ranked = compare_metric(
        comparison_ready,
        metric_id="gdp_per_capita",
        countries_include=["ISR"],
        year_strategy=YearStrategy.TARGET_YEAR,
        target_year=2023,
        normalization_method="minmax",
    )
    assert ranked.loc[0, "country_code"] == "ISR"
    assert ranked.loc[0, "year"] == 2023
    assert ranked.loc[0, "rank"] == 1
