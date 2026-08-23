from __future__ import annotations

import math

import pandas as pd
import pytest

from country_compare.prediction import (
    ForecastOptions,
    PredictionDiagnosticStatus,
    PredictionErrorCode,
    PredictionException,
    PredictionMethod,
    SingleMetricPredictionRequest,
    list_available_prediction_methods,
    predict_single_metric,
)
from country_compare.prediction.ml_forecasters import is_elasticnet_available


def _prediction_oracle_dataframe(
    *,
    years: tuple[int, ...],
    values: tuple[float, ...],
) -> pd.DataFrame:
    assert len(years) == len(values)

    return pd.DataFrame(
        [
            {
                "country_code": "AAA",
                "country_name": "Alpha",
                "metric_id": "oracle_metric",
                "metric_name": "Oracle Metric",
                "value": float(value),
                "year": year,
                "unit": "oracle_unit",
                "source_name": "Validation oracle",
                "source_url": "https://example.test/validation-oracle",
                "higher_is_better": True,
                "category": "validation",
                "dataset_version": "oracle-v1",
                "region": "Oracle Region",
                "income_group": "Oracle Income",
                "notes": None,
            }
            for year, value in zip(years, values, strict=True)
        ]
    )


def _prediction_oracle_request(
    *,
    method: PredictionMethod,
    horizon_years: int,
) -> SingleMetricPredictionRequest:
    return SingleMetricPredictionRequest(
        country_code="AAA",
        metric_id="oracle_metric",
        horizon_years=horizon_years,
        method=method,
        fallback_method=PredictionMethod.LAST_OBSERVED,
    )


def test_pred_01_last_observed_matches_independent_oracle() -> None:
    dataframe = _prediction_oracle_dataframe(
        years=(2019, 2020, 2021, 2022),
        values=(4.0, 7.0, 11.0, 13.0),
    )

    result = predict_single_metric(
        dataframe,
        _prediction_oracle_request(
            method=PredictionMethod.LAST_OBSERVED,
            horizon_years=3,
        ),
    )

    # Independent oracle:
    #
    # Last actual observation:
    #   2022 -> 13.0
    #
    # last_observed therefore produces:
    #   2023 -> 13.0
    #   2024 -> 13.0
    #   2025 -> 13.0

    assert result.forecast_df["year"].tolist() == [2023, 2024, 2025]
    assert result.forecast_df["forecast_horizon"].tolist() == [1, 2, 3]
    assert result.forecast_df["value"].tolist() == pytest.approx(
        [13.0, 13.0, 13.0],
        abs=1e-12,
    )

    diagnostic = result.diagnostics[0]

    assert diagnostic.status == PredictionDiagnosticStatus.OK
    assert diagnostic.method_requested == "last_observed"
    assert diagnostic.method_used == "last_observed"
    assert diagnostic.fallback_used is False

    info = result.forecaster_info[0]

    assert info.method_id == "last_observed"
    assert info.metadata["latest_observed_value"] == pytest.approx(
        13.0,
        abs=1e-12,
    )


def test_pred_02_moving_average_matches_independent_recent_window_oracle() -> None:
    dataframe = _prediction_oracle_dataframe(
        years=(2019, 2020, 2021, 2022, 2023),
        values=(2.0, 4.0, 8.0, 16.0, 32.0),
    )

    result = predict_single_metric(
        dataframe,
        _prediction_oracle_request(
            method=PredictionMethod.MOVING_AVERAGE,
            horizon_years=3,
        ),
    )

    # Independent oracle:
    #
    # The configured/default window size is 3.
    #
    # Most recent observations:
    #   2021 ->  8
    #   2022 -> 16
    #   2023 -> 32
    #
    # Moving average:
    #   (8 + 16 + 32) / 3
    #   = 56 / 3
    #   = 18.666666666666...
    #
    # The same value is forecast for every horizon.
    expected_value = 56.0 / 3.0

    assert result.forecast_df["year"].tolist() == [2024, 2025, 2026]
    assert result.forecast_df["forecast_horizon"].tolist() == [1, 2, 3]
    assert result.forecast_df["value"].tolist() == pytest.approx(
        [expected_value, expected_value, expected_value],
        abs=1e-12,
    )

    diagnostic = result.diagnostics[0]

    assert diagnostic.status == PredictionDiagnosticStatus.OK
    assert diagnostic.method_requested == "moving_average"
    assert diagnostic.method_used == "moving_average"
    assert diagnostic.fallback_used is False

    info = result.forecaster_info[0]

    assert info.method_id == "moving_average"
    assert info.metadata["window_size"] == 3
    assert info.metadata["effective_window_size"] == 3
    assert info.metadata["input_years_used"] == [2021, 2022, 2023]
    assert info.metadata["moving_average_value"] == pytest.approx(
        expected_value,
        abs=1e-12,
    )


def test_pred_03_linear_trend_matches_independent_least_squares_oracle() -> None:
    dataframe = _prediction_oracle_dataframe(
        years=(2020, 2021, 2022, 2023),
        values=(10.0, 20.0, 30.0, 40.0),
    )

    result = predict_single_metric(
        dataframe,
        _prediction_oracle_request(
            method=PredictionMethod.LINEAR_TREND,
            horizon_years=3,
        ),
    )

    # Independent least-squares oracle:
    #
    # x = [2020, 2021, 2022, 2023]
    # y = [10,   20,   30,   40]
    #
    # x_mean = 2021.5
    # y_mean = 25
    #
    # x deviations:
    #   [-1.5, -0.5, 0.5, 1.5]
    #
    # y deviations:
    #   [-15, -5, 5, 15]
    #
    # numerator:
    #   22.5 + 2.5 + 2.5 + 22.5 = 50
    #
    # denominator:
    #   2.25 + 0.25 + 0.25 + 2.25 = 5
    #
    # slope = 50 / 5 = 10
    #
    # intercept:
    #   25 - (10 * 2021.5)
    #   = -20190
    #
    # Forecasts:
    #   2024 -> 50
    #   2025 -> 60
    #   2026 -> 70

    assert result.forecast_df["year"].tolist() == [2024, 2025, 2026]
    assert result.forecast_df["forecast_horizon"].tolist() == [1, 2, 3]
    assert result.forecast_df["value"].tolist() == pytest.approx(
        [50.0, 60.0, 70.0],
        abs=1e-9,
    )

    diagnostic = result.diagnostics[0]

    assert diagnostic.status == PredictionDiagnosticStatus.OK
    assert diagnostic.method_requested == "linear_trend"
    assert diagnostic.method_used == "linear_trend"
    assert diagnostic.fallback_used is False

    info = result.forecaster_info[0]

    assert info.method_id == "linear_trend"
    assert info.metadata["slope"] == pytest.approx(10.0, abs=1e-12)
    assert info.metadata["intercept"] == pytest.approx(
        -20190.0,
        abs=1e-9,
    )


def test_pred_04_holt_linear_matches_independent_frozen_oracle() -> None:
    dataframe = _prediction_oracle_dataframe(
        years=(2019, 2020, 2021, 2022, 2023),
        values=(12.0, 18.0, 15.0, 27.0, 24.0),
    )

    result = predict_single_metric(
        dataframe,
        _prediction_oracle_request(
            method=PredictionMethod.HOLT_LINEAR,
            horizon_years=3,
        ),
    )

    # Independent Holt-linear oracle.
    #
    # Production contract:
    #   alpha = 0.8
    #   beta = 0.2
    #   damped = True
    #   phi = 0.9
    #
    # Initial level:
    #   L0 = 12
    #
    # Initial trend is the mean annual difference:
    #
    #   differences:
    #     18 - 12 =  6
    #     15 - 18 = -3
    #     27 - 15 = 12
    #     24 - 27 = -3
    #
    #   initial trend:
    #     (6 - 3 + 12 - 3) / 4 = 3
    #
    # Each one-year projected level uses:
    #
    #   projected = previous_level + phi * previous_trend
    #
    # Level update:
    #
    #   level =
    #       alpha * observation
    #       + (1 - alpha) * projected
    #
    # Trend update:
    #
    #   annual_delta = level - previous_level
    #
    #   trend =
    #       beta * annual_delta
    #       + (1 - beta) * phi * previous_trend
    #
    # Step results, calculated independently:
    #
    # 2020:
    #   projected = 12 + 0.9*3
    #             = 14.7
    #
    #   level = 0.8*18 + 0.2*14.7
    #         = 17.34
    #
    #   trend = 0.2*(17.34 - 12) + 0.8*(0.9*3)
    #         = 3.228
    #
    # 2021:
    #   projected = 17.34 + 0.9*3.228
    #             = 20.2452
    #
    #   level = 0.8*15 + 0.2*20.2452
    #         = 16.04904
    #
    #   trend = 2.065968
    #
    # 2022:
    #   level = 25.18168224
    #   trend = 3.314025408
    #
    # 2023:
    #   final level = 24.83286102144
    #   final trend = 2.316334050048
    #
    # Future damped trend contribution for horizon h is:
    #
    #   trend * (phi + phi^2 + ... + phi^h)
    #
    # Therefore:
    #
    # 2024:
    #   24.83286102144
    #   + 2.316334050048*(0.9)
    #   = 26.9175616664832
    #
    # 2025:
    #   24.83286102144
    #   + 2.316334050048*(0.9 + 0.9^2)
    #   = 28.7937922470221
    #
    # 2026:
    #   24.83286102144
    #   + 2.316334050048*(0.9 + 0.9^2 + 0.9^3)
    #   = 30.4823997695071

    expected_values = [
        26.917561666483206,
        28.793792247022086,
        30.482399769507076,
    ]

    assert result.forecast_df["year"].tolist() == [2024, 2025, 2026]
    assert result.forecast_df["forecast_horizon"].tolist() == [1, 2, 3]

    assert result.forecast_df["value"].tolist() == pytest.approx(
        expected_values,
        abs=1e-9,
    )

    diagnostic = result.diagnostics[0]

    assert diagnostic.status == PredictionDiagnosticStatus.OK
    assert diagnostic.method_requested == "holt_linear"
    assert diagnostic.method_used == "holt_linear"
    assert diagnostic.fallback_used is False
    assert diagnostic.warnings == []

    info = result.forecaster_info[0]

    assert info.method_id == "holt_linear"

    assert info.metadata["alpha"] == pytest.approx(0.8, abs=1e-12)
    assert info.metadata["beta"] == pytest.approx(0.2, abs=1e-12)
    assert info.metadata["damped"] is True
    assert info.metadata["phi"] == pytest.approx(0.9, abs=1e-12)

    assert info.metadata["training_observation_count"] == 5
    assert info.metadata["training_year_min"] == 2019
    assert info.metadata["training_year_max"] == 2023

    assert info.metadata["final_level"] == pytest.approx(
        24.832861021440003,
        abs=1e-9,
    )
    assert info.metadata["final_trend"] == pytest.approx(
        2.316334050048001,
        abs=1e-9,
    )


def test_pred_05_elasticnet_runtime_capability_matches_method_catalog() -> None:
    available = is_elasticnet_available()

    method_catalog = list_available_prediction_methods()
    method_ids = {str(method["method_id"]) for method in method_catalog}

    assert ("elasticnet_trend" in method_ids) is available

    dataframe = _prediction_oracle_dataframe(
        years=(
            2015,
            2016,
            2017,
            2018,
            2019,
            2020,
            2021,
            2022,
            2023,
        ),
        values=(
            100.0,
            103.0,
            107.0,
            112.0,
            118.0,
            125.0,
            133.0,
            142.0,
            152.0,
        ),
    )

    request = SingleMetricPredictionRequest(
        country_code="AAA",
        metric_id="oracle_metric",
        horizon_years=3,
        method=PredictionMethod.ELASTICNET_TREND,
        fallback_method=None,
    )

    if not available:
        with pytest.raises(PredictionException) as exc_info:
            predict_single_metric(dataframe, request)

        exc = exc_info.value

        assert exc.code == PredictionErrorCode.UNSUPPORTED_METHOD
        assert exc.details["method"] == "elasticnet_trend"
        assert "elasticnet_trend" in exc.message

        return

    result = predict_single_metric(dataframe, request)

    assert result.forecast_df["year"].tolist() == [2024, 2025, 2026]
    assert result.forecast_df["forecast_horizon"].tolist() == [1, 2, 3]

    forecast_values = [float(value) for value in result.forecast_df["value"].tolist()]

    assert len(forecast_values) == 3
    assert all(math.isfinite(value) for value in forecast_values)

    diagnostic = result.diagnostics[0]

    assert diagnostic.status == PredictionDiagnosticStatus.OK
    assert diagnostic.method_requested == "elasticnet_trend"
    assert diagnostic.method_used == "elasticnet_trend"
    assert diagnostic.fallback_used is False

    info = result.forecaster_info[0]

    assert info.method_id == "elasticnet_trend"
    assert info.metadata["alpha"] == pytest.approx(0.1)
    assert info.metadata["l1_ratio"] == pytest.approx(0.5)
    assert info.metadata["training_observation_count"] == 9
    assert info.metadata["training_start_year"] == 2015
    assert info.metadata["training_end_year"] == 2023
    assert info.metadata["feature_columns"] == [
        "year_offset",
        "year_offset_squared",
    ]


def test_pred_06_horizon_boundaries_accept_min_and_max_and_reject_above_max() -> None:
    dataframe = _prediction_oracle_dataframe(
        years=(2020, 2021, 2022, 2023),
        values=(10.0, 20.0, 30.0, 40.0),
    )

    options = ForecastOptions(max_horizon_years=10)

    minimum_result = predict_single_metric(
        dataframe,
        SingleMetricPredictionRequest(
            country_code="AAA",
            metric_id="oracle_metric",
            horizon_years=1,
            method=PredictionMethod.LAST_OBSERVED,
        ),
        options=options,
    )

    assert len(minimum_result.forecast_df.index) == 1
    assert minimum_result.forecast_df["year"].tolist() == [2024]
    assert minimum_result.forecast_df["forecast_horizon"].tolist() == [1]
    assert minimum_result.forecast_df["value"].tolist() == pytest.approx(
        [40.0],
        abs=1e-12,
    )

    maximum_result = predict_single_metric(
        dataframe,
        SingleMetricPredictionRequest(
            country_code="AAA",
            metric_id="oracle_metric",
            horizon_years=10,
            method=PredictionMethod.LAST_OBSERVED,
        ),
        options=options,
    )

    assert len(maximum_result.forecast_df.index) == 10
    assert maximum_result.forecast_df["year"].tolist() == list(range(2024, 2034))
    assert maximum_result.forecast_df["forecast_horizon"].tolist() == list(range(1, 11))
    assert maximum_result.forecast_df["value"].tolist() == pytest.approx(
        [40.0] * 10,
        abs=1e-12,
    )

    with pytest.raises(PredictionException) as exc_info:
        predict_single_metric(
            dataframe,
            SingleMetricPredictionRequest(
                country_code="AAA",
                metric_id="oracle_metric",
                horizon_years=11,
                method=PredictionMethod.LAST_OBSERVED,
            ),
            options=options,
        )

    exc = exc_info.value

    assert exc.code == PredictionErrorCode.INVALID_HORIZON
    assert exc.details == {
        "horizon_years": 11,
        "max_horizon_years": 10,
    }
    assert exc.message == "horizon_years must be <= 10"


def test_pred_07_include_actuals_controls_combined_output_only() -> None:
    dataframe = _prediction_oracle_dataframe(
        years=(2020, 2021, 2022),
        values=(10.0, 20.0, 30.0),
    )

    with_actuals = predict_single_metric(
        dataframe,
        SingleMetricPredictionRequest(
            country_code="AAA",
            metric_id="oracle_metric",
            horizon_years=2,
            method=PredictionMethod.LAST_OBSERVED,
            include_actuals=True,
        ),
    )

    without_actuals = predict_single_metric(
        dataframe,
        SingleMetricPredictionRequest(
            country_code="AAA",
            metric_id="oracle_metric",
            horizon_years=2,
            method=PredictionMethod.LAST_OBSERVED,
            include_actuals=False,
        ),
    )

    # include_actuals must not change the forecast calculation itself.
    assert with_actuals.forecast_df["year"].tolist() == [2023, 2024]
    assert without_actuals.forecast_df["year"].tolist() == [2023, 2024]

    assert with_actuals.forecast_df["value"].tolist() == pytest.approx(
        [30.0, 30.0],
        abs=1e-12,
    )
    assert without_actuals.forecast_df["value"].tolist() == pytest.approx(
        [30.0, 30.0],
        abs=1e-12,
    )

    # When actuals are included, historical and predicted rows are
    # unambiguously distinguishable.
    assert with_actuals.combined_df["year"].tolist() == [
        2020,
        2021,
        2022,
        2023,
        2024,
    ]
    assert with_actuals.combined_df["row_type"].tolist() == [
        "actual",
        "actual",
        "actual",
        "predicted",
        "predicted",
    ]
    assert with_actuals.combined_df["is_predicted"].tolist() == [
        False,
        False,
        False,
        True,
        True,
    ]
    assert with_actuals.combined_df["forecast_horizon"].tolist() == [
        0,
        0,
        0,
        1,
        2,
    ]

    # With include_actuals=False, combined_df contains forecast rows only.
    assert without_actuals.combined_df["year"].tolist() == [2023, 2024]
    assert without_actuals.combined_df["row_type"].tolist() == [
        "predicted",
        "predicted",
    ]
    assert without_actuals.combined_df["is_predicted"].tolist() == [
        True,
        True,
    ]
    assert without_actuals.combined_df["forecast_horizon"].tolist() == [1, 2]


def test_pred_08_history_window_uses_only_requested_years() -> None:
    dataframe = _prediction_oracle_dataframe(
        years=(
            2018,
            2019,
            2020,
            2021,
            2022,
            2023,
            2024,
        ),
        values=(
            1000.0,
            1000.0,
            10.0,
            20.0,
            30.0,
            -1000.0,
            -1000.0,
        ),
    )

    result = predict_single_metric(
        dataframe,
        SingleMetricPredictionRequest(
            country_code="AAA",
            metric_id="oracle_metric",
            horizon_years=2,
            method=PredictionMethod.LINEAR_TREND,
            history_start_year=2020,
            history_end_year=2022,
            include_actuals=True,
        ),
    )

    # Independent oracle:
    #
    # Only these three observations are legal training input:
    #
    #   2020 -> 10
    #   2021 -> 20
    #   2022 -> 30
    #
    # slope = +10 per year
    #
    # Therefore:
    #   2023 -> 40
    #   2024 -> 50
    #
    # The values in 2018/2019 and 2023/2024 must have no influence.

    assert result.forecast_df["year"].tolist() == [2023, 2024]
    assert result.forecast_df["value"].tolist() == pytest.approx(
        [40.0, 50.0],
        abs=1e-9,
    )

    diagnostic = result.diagnostics[0]

    assert diagnostic.status == PredictionDiagnosticStatus.OK
    assert diagnostic.history_observation_count == 3
    assert diagnostic.training_start_year == 2020
    assert diagnostic.training_end_year == 2022
    assert diagnostic.forecast_origin_year == 2022
    assert diagnostic.missing_years == []

    info = result.forecaster_info[0]

    assert info.method_id == "linear_trend"
    assert info.metadata["slope"] == pytest.approx(10.0, abs=1e-12)

    actual_rows = result.combined_df.loc[result.combined_df["row_type"].eq("actual")]

    assert actual_rows["year"].tolist() == [2020, 2021, 2022]
    assert actual_rows["value"].tolist() == pytest.approx(
        [10.0, 20.0, 30.0],
        abs=1e-12,
    )


def test_pred_09_insufficient_history_uses_configured_fallback_with_diagnostics() -> (
    None
):
    dataframe = _prediction_oracle_dataframe(
        years=(2021, 2022),
        values=(10.0, 20.0),
    )

    result = predict_single_metric(
        dataframe,
        SingleMetricPredictionRequest(
            country_code="AAA",
            metric_id="oracle_metric",
            horizon_years=2,
            method=PredictionMethod.LINEAR_TREND,
            fallback_method=PredictionMethod.LAST_OBSERVED,
        ),
    )

    # Independent fallback oracle:
    #
    # linear_trend requires >= 3 observations, so the two-point
    # series is unsupported.
    #
    # Configured fallback = last_observed.
    #
    # Latest observed value:
    #   2022 -> 20
    #
    # Therefore:
    #   2023 -> 20
    #   2024 -> 20

    assert result.forecast_df["year"].tolist() == [2023, 2024]
    assert result.forecast_df["forecast_horizon"].tolist() == [1, 2]
    assert result.forecast_df["value"].tolist() == pytest.approx(
        [20.0, 20.0],
        abs=1e-12,
    )

    diagnostic = result.diagnostics[0]

    assert diagnostic.status == PredictionDiagnosticStatus.WARNING
    assert diagnostic.method_requested == "linear_trend"
    assert diagnostic.method_used == "last_observed"
    assert diagnostic.fallback_used is True

    assert diagnostic.history_observation_count == 2
    assert diagnostic.training_start_year == 2021
    assert diagnostic.training_end_year == 2022
    assert diagnostic.forecast_origin_year == 2022

    assert any(
        "used fallback method 'last_observed'" in warning
        for warning in diagnostic.warnings
    )
    assert any(
        "linear_trend requires at least three observations" in warning
        for warning in diagnostic.warnings
    )

    assert result.metadata["method_requested"] == "linear_trend"
    assert result.metadata["method_used"] == "last_observed"
    assert result.metadata["fallback_used"] is True

    info = result.forecaster_info[0]

    assert info.method_id == "last_observed"
    assert info.metadata["latest_observed_value"] == pytest.approx(
        20.0,
        abs=1e-12,
    )

    assert result.forecast_df["prediction_method"].tolist() == [
        "last_observed",
        "last_observed",
    ]
    assert result.forecast_df["diagnostic_status"].tolist() == [
        "warning",
        "warning",
    ]

    assert all(
        "fallback" in message
        for message in result.forecast_df["diagnostic_messages"].tolist()
    )
