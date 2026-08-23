from __future__ import annotations

import math

import pandas as pd
import pytest

import country_compare.prediction.multi_metric as prediction_multi_metric
from country_compare.config.models import (
    MetricConfig,
    MetricsConfig,
    MissingDataPolicy,
    NormalizationMethod,
    ScoringConfig,
    ScoringProfile,
    WeightHandlingStrategy,
    YearStrategy,
)
from country_compare.prediction import (
    ForecastOptions,
    PredictionDiagnosticStatus,
    PredictionErrorCode,
    PredictionException,
    PredictionMethod,
    SingleMetricPredictionRequest,
    backtest_series,
    compare_predicted_multi_metric,
    compare_predicted_profile,
    compare_predicted_single_metric,
    list_available_prediction_methods,
    predict_single_metric,
    predict_single_metric_for_countries,
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


def _multi_country_prediction_oracle_dataframe() -> pd.DataFrame:
    series = {
        "AAA": {
            "country_name": "Alpha",
            "years": (2020, 2021, 2022, 2023),
            "values": (10.0, 20.0, 30.0, 40.0),
        },
        "BBB": {
            "country_name": "Beta",
            "years": (2020, 2021, 2022, 2023),
            "values": (100.0, 85.0, 70.0, 55.0),
        },
        # Deliberately insufficient for linear_trend.
        "CCC": {
            "country_name": "Gamma",
            "years": (2023,),
            "values": (500.0,),
        },
    }

    rows: list[dict[str, object]] = []

    for country_code, definition in series.items():
        country_name = str(definition["country_name"])
        years = definition["years"]
        values = definition["values"]

        for year, value in zip(years, values, strict=True):
            rows.append(
                {
                    "country_code": country_code,
                    "country_name": country_name,
                    "metric_id": "oracle_metric",
                    "metric_name": "Oracle Metric",
                    "value": float(value),
                    "year": int(year),
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
            )

    return pd.DataFrame(rows)


def _backtest_oracle_dataframe(
    *,
    holdout_values: tuple[float, float] = (50.0, 70.0),
) -> pd.DataFrame:
    return _prediction_oracle_dataframe(
        years=(2018, 2019, 2020, 2021, 2022),
        values=(10.0, 20.0, 30.0, *holdout_values),
    )


def _run_backtest_oracle():
    return backtest_series(
        _backtest_oracle_dataframe(),
        country_code="AAA",
        metric_id="oracle_metric",
        method=PredictionMethod.LAST_OBSERVED,
        fallback_method=None,
        holdout_years=2,
        scenario_id="validation-backtest",
    )


def _predicted_comparison_oracle_dataframe() -> pd.DataFrame:
    country_names = {
        "AAA": "Alpha",
        "BBB": "Beta",
        "CCC": "Gamma",
    }

    metric_definitions = {
        "metric_alpha": {
            "metric_name": "Metric Alpha",
            "higher_is_better": True,
            "values": {
                2022: {
                    "AAA": 5.0,
                    "BBB": 15.0,
                    "CCC": 25.0,
                },
                2023: {
                    "AAA": 10.0,
                    "BBB": 20.0,
                    "CCC": 30.0,
                },
            },
        },
        "metric_beta": {
            "metric_name": "Metric Beta",
            "higher_is_better": False,
            "values": {
                2022: {
                    "AAA": 35.0,
                    "BBB": 15.0,
                    "CCC": 25.0,
                },
                2023: {
                    "AAA": 30.0,
                    "BBB": 10.0,
                    "CCC": 20.0,
                },
            },
        },
    }

    rows: list[dict[str, object]] = []

    for metric_id, definition in metric_definitions.items():
        values_by_year = definition["values"]

        for year, country_values in values_by_year.items():
            for country_code, value in country_values.items():
                rows.append(
                    {
                        "country_code": country_code,
                        "country_name": country_names[country_code],
                        "metric_id": metric_id,
                        "metric_name": definition["metric_name"],
                        "value": float(value),
                        "year": int(year),
                        "unit": "oracle_unit",
                        "source_name": "Validation oracle",
                        "source_url": "https://example.test/validation-oracle",
                        "higher_is_better": bool(definition["higher_is_better"]),
                        "category": "validation",
                        "dataset_version": "oracle-v1",
                        "region": "Oracle Region",
                        "income_group": "Oracle Income",
                        "notes": None,
                    }
                )

    return pd.DataFrame(rows)


def _predicted_profile_oracle_configs() -> tuple[
    MetricsConfig,
    ScoringConfig,
]:
    metrics_config = MetricsConfig(
        metrics={
            "metric_alpha": MetricConfig(
                display_name="Metric Alpha",
                category="validation",
                higher_is_better=True,
                default_weight=0.6,
                unit="oracle_unit",
                normalization_method=NormalizationMethod.MINMAX,
            ),
            "metric_beta": MetricConfig(
                display_name="Metric Beta",
                category="validation",
                higher_is_better=False,
                default_weight=0.4,
                unit="oracle_unit",
                normalization_method=NormalizationMethod.MINMAX,
            ),
        }
    )

    scoring_config = ScoringConfig(
        default_profile="oracle_profile",
        weight_handling=WeightHandlingStrategy.NORMALIZE,
        default_year_strategy=YearStrategy.LATEST_PER_METRIC,
        default_missing_data_policy=MissingDataPolicy.RENORMALIZE_WEIGHTS,
        profiles={
            "oracle_profile": ScoringProfile(
                metrics=["metric_alpha", "metric_beta"],
                weights={
                    "metric_alpha": 0.6,
                    "metric_beta": 0.4,
                },
                normalization_overrides={
                    "metric_alpha": NormalizationMethod.MINMAX,
                    "metric_beta": NormalizationMethod.MINMAX,
                },
                year_strategy=YearStrategy.LATEST_PER_METRIC,
                missing_data_policy=MissingDataPolicy.RENORMALIZE_WEIGHTS,
            )
        },
    )

    return metrics_config, scoring_config


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


def test_pred_10_partial_failure_keeps_successful_country_forecasts() -> None:
    dataframe = _multi_country_prediction_oracle_dataframe()

    result = predict_single_metric_for_countries(
        dataframe,
        metric_id="oracle_metric",
        country_codes=["AAA", "CCC", "BBB"],
        horizon_years=2,
        method=PredictionMethod.LINEAR_TREND,
        fallback_method=None,
        include_actuals=False,
        fail_fast=False,
    )

    # AAA and BBB are forecastable; CCC is not.
    assert result.metadata["successful_series_count"] == 2
    assert result.metadata["failed_series_count"] == 1
    assert result.metadata["all_series_failed"] is False

    assert result.metadata["successful_pairs"] == [
        {
            "country_code": "AAA",
            "metric_id": "oracle_metric",
        },
        {
            "country_code": "BBB",
            "metric_id": "oracle_metric",
        },
    ]

    assert result.metadata["failed_pairs"] == [
        {
            "country_code": "CCC",
            "metric_id": "oracle_metric",
        }
    ]

    # Independent forecast oracles:
    #
    # AAA:
    #   y increases by 10/year
    #   2024 -> 50
    #   2025 -> 60
    #
    # BBB:
    #   y decreases by 15/year
    #   2024 -> 40
    #   2025 -> 25
    #
    # CCC must produce no forecast rows.

    aaa = result.forecast_df.loc[result.forecast_df["country_code"].eq("AAA")]

    assert aaa["year"].tolist() == [2024, 2025]
    assert aaa["value"].tolist() == pytest.approx(
        [50.0, 60.0],
        abs=1e-9,
    )

    bbb = result.forecast_df.loc[result.forecast_df["country_code"].eq("BBB")]

    assert bbb["year"].tolist() == [2024, 2025]
    assert bbb["value"].tolist() == pytest.approx(
        [40.0, 25.0],
        abs=1e-9,
    )

    assert "CCC" not in set(result.forecast_df["country_code"])

    failed = [
        diagnostic
        for diagnostic in result.diagnostics
        if diagnostic.status == PredictionDiagnosticStatus.FAILED
    ]

    assert len(failed) == 1

    diagnostic = failed[0]

    assert diagnostic.country_code == "CCC"
    assert diagnostic.metric_id == "oracle_metric"
    assert diagnostic.method_requested == "linear_trend"
    assert diagnostic.method_used is None
    assert diagnostic.fallback_used is False

    assert len(diagnostic.errors) == 1

    error = diagnostic.errors[0]

    assert error.code == PredictionErrorCode.INSUFFICIENT_HISTORY
    assert error.country_code == "CCC"
    assert error.metric_id == "oracle_metric"

    assert "requires at least three observations" in error.message


def test_pred_11_fail_fast_stops_after_first_failed_series(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    dataframe = _multi_country_prediction_oracle_dataframe()

    original_predict_single_metric = prediction_multi_metric.predict_single_metric

    attempted_countries: list[str] = []

    def recording_predict_single_metric(
        canonical_df: pd.DataFrame,
        request: SingleMetricPredictionRequest,
        *,
        options: ForecastOptions | None = None,
    ):
        attempted_countries.append(request.country_code)

        return original_predict_single_metric(
            canonical_df,
            request,
            options=options,
        )

    monkeypatch.setattr(
        prediction_multi_metric,
        "predict_single_metric",
        recording_predict_single_metric,
    )

    with pytest.raises(PredictionException) as exc_info:
        predict_single_metric_for_countries(
            dataframe,
            metric_id="oracle_metric",
            country_codes=["AAA", "CCC", "BBB"],
            horizon_years=2,
            method=PredictionMethod.LINEAR_TREND,
            fallback_method=None,
            include_actuals=False,
            fail_fast=True,
        )

    # AAA succeeds first.
    # CCC then fails.
    # BBB must never be attempted.
    assert attempted_countries == ["AAA", "CCC"]

    exc = exc_info.value

    assert exc.code == PredictionErrorCode.INSUFFICIENT_HISTORY
    assert exc.country_code == "CCC"
    assert exc.metric_id == "oracle_metric"

    assert "linear_trend requires at least three observations" in exc.message


def test_pred_12_multi_country_forecasts_match_independent_per_country_oracles() -> (
    None
):
    dataframe = _multi_country_prediction_oracle_dataframe()

    result = predict_single_metric_for_countries(
        dataframe,
        metric_id="oracle_metric",
        country_codes=["AAA", "BBB"],
        horizon_years=3,
        method=PredictionMethod.LINEAR_TREND,
        fallback_method=None,
        include_actuals=False,
        fail_fast=True,
    )

    assert result.metadata["successful_series_count"] == 2
    assert result.metadata["failed_series_count"] == 0
    assert result.metadata["failed_pairs"] == []
    assert result.metadata["all_series_failed"] is False

    # Independent AAA oracle:
    #
    # 2020 -> 10
    # 2021 -> 20
    # 2022 -> 30
    # 2023 -> 40
    #
    # slope = +10
    #
    # 2024 -> 50
    # 2025 -> 60
    # 2026 -> 70
    aaa = result.forecast_df.loc[result.forecast_df["country_code"].eq("AAA")]

    assert aaa["year"].tolist() == [2024, 2025, 2026]
    assert aaa["forecast_horizon"].tolist() == [1, 2, 3]
    assert aaa["value"].tolist() == pytest.approx(
        [50.0, 60.0, 70.0],
        abs=1e-9,
    )

    # Independent BBB oracle:
    #
    # 2020 -> 100
    # 2021 ->  85
    # 2022 ->  70
    # 2023 ->  55
    #
    # slope = -15
    #
    # 2024 -> 40
    # 2025 -> 25
    # 2026 -> 10
    bbb = result.forecast_df.loc[result.forecast_df["country_code"].eq("BBB")]

    assert bbb["year"].tolist() == [2024, 2025, 2026]
    assert bbb["forecast_horizon"].tolist() == [1, 2, 3]
    assert bbb["value"].tolist() == pytest.approx(
        [40.0, 25.0, 10.0],
        abs=1e-9,
    )

    diagnostics_by_country = {
        diagnostic.country_code: diagnostic for diagnostic in result.diagnostics
    }

    assert set(diagnostics_by_country) == {"AAA", "BBB"}

    for country_code in ("AAA", "BBB"):
        diagnostic = diagnostics_by_country[country_code]

        assert diagnostic.status == PredictionDiagnosticStatus.OK
        assert diagnostic.method_requested == "linear_trend"
        assert diagnostic.method_used == "linear_trend"
        assert diagnostic.fallback_used is False
        assert diagnostic.history_observation_count == 4
        assert diagnostic.training_start_year == 2020
        assert diagnostic.training_end_year == 2023
        assert diagnostic.forecast_origin_year == 2023

    # Every successful series in one batch should share the batch-level
    # prediction run identity.
    assert result.forecast_df["prediction_run_id"].nunique() == 1


def test_pred_14_backtest_split_has_no_future_leakage() -> None:
    result = _run_backtest_oracle()

    dataframe = result.actual_vs_predicted_df

    assert dataframe["year"].tolist() == [2021, 2022]
    assert dataframe["actual_value"].tolist() == pytest.approx(
        [50.0, 70.0],
        abs=1e-12,
    )

    # Independent oracle:
    # the final TRAINING value is 30, so last_observed must forecast 30
    # for both held-out years. If holdout observations leaked into training,
    # this would not hold.
    assert dataframe["predicted_value"].tolist() == pytest.approx(
        [30.0, 30.0],
        abs=1e-12,
    )

    diagnostic = result.diagnostics[0]

    assert diagnostic.history_observation_count == 3
    assert diagnostic.training_start_year == 2018
    assert diagnostic.training_end_year == 2020
    assert diagnostic.forecast_origin_year == 2020

    assert result.metrics["n_train_observations"] == 3
    assert result.metrics["n_test_observations"] == 2
    assert result.metrics["train_start_year"] == 2018
    assert result.metrics["train_end_year"] == 2020
    assert result.metrics["test_start_year"] == 2021
    assert result.metrics["test_end_year"] == 2022

    assert result.metadata["holdout_years"] == [2021, 2022]
    assert result.metadata["forecast_origin_year"] == 2020

    assert dataframe["training_start_year"].tolist() == [2018, 2018]
    assert dataframe["training_end_year"].tolist() == [2020, 2020]
    assert dataframe["forecast_origin_year"].tolist() == [2020, 2020]


def test_pred_15_backtest_mae_matches_independent_oracle() -> None:
    result = _run_backtest_oracle()

    dataframe = result.actual_vs_predicted_df

    # predicted - actual:
    #
    # 2021: 30 - 50 = -20
    # 2022: 30 - 70 = -40
    #
    # absolute errors:
    #   20, 40
    #
    # MAE:
    #   (20 + 40) / 2 = 30

    assert dataframe["error"].tolist() == pytest.approx(
        [-20.0, -40.0],
        abs=1e-12,
    )
    assert dataframe["absolute_error"].tolist() == pytest.approx(
        [20.0, 40.0],
        abs=1e-12,
    )

    assert result.metrics["mae"] == pytest.approx(
        30.0,
        abs=1e-12,
    )


def test_pred_16_backtest_rmse_matches_independent_oracle() -> None:
    result = _run_backtest_oracle()

    dataframe = result.actual_vs_predicted_df

    # Squared errors:
    #
    #   (-20)^2 = 400
    #   (-40)^2 = 1600
    #
    # Mean squared error:
    #
    #   (400 + 1600) / 2 = 1000
    #
    # RMSE:
    #
    #   sqrt(1000)
    #   = 31.622776601683793

    assert dataframe["squared_error"].tolist() == pytest.approx(
        [400.0, 1600.0],
        abs=1e-12,
    )

    assert result.metrics["rmse"] == pytest.approx(
        math.sqrt(1000.0),
        abs=1e-12,
    )


def test_pred_17_backtest_mape_matches_oracle_and_handles_zero_actual() -> None:
    result = _run_backtest_oracle()

    dataframe = result.actual_vs_predicted_df

    # Absolute percentage errors:
    #
    # 2021:
    #   |30 - 50| / |50|
    #   = 20 / 50
    #   = 0.4
    #
    # 2022:
    #   |30 - 70| / |70|
    #   = 40 / 70
    #   = 4 / 7
    #
    # MAPE:
    #
    #   (0.4 + 4/7) / 2
    #   = 17/35
    #   = 0.485714285714...

    expected_ape = [
        0.4,
        4.0 / 7.0,
    ]

    assert dataframe["absolute_percentage_error"].tolist() == pytest.approx(
        expected_ape,
        abs=1e-12,
    )

    assert result.metrics["mape"] == pytest.approx(
        17.0 / 35.0,
        abs=1e-12,
    )

    zero_actual_result = backtest_series(
        _backtest_oracle_dataframe(
            holdout_values=(0.0, 60.0),
        ),
        country_code="AAA",
        metric_id="oracle_metric",
        method=PredictionMethod.LAST_OBSERVED,
        fallback_method=None,
        holdout_years=2,
    )

    zero_dataframe = zero_actual_result.actual_vs_predicted_df

    # Training still ends at:
    #   2020 -> 30
    #
    # Forecast:
    #   2021 -> 30, actual = 0
    #   2022 -> 30, actual = 60
    #
    # Division by zero must never occur. The per-row APE for 2021 is
    # missing, and the current aggregate contract marks MAPE undefined
    # for the complete backtest if any held-out actual equals zero.

    ape = zero_dataframe["absolute_percentage_error"].tolist()

    assert pd.isna(ape[0])
    assert ape[1] == pytest.approx(0.5, abs=1e-12)

    assert zero_actual_result.metrics["mape"] is None


def test_pred_18_predicted_single_metric_matches_forecast_and_comparison_oracle() -> (
    None
):
    dataframe = _predicted_comparison_oracle_dataframe()

    result = compare_predicted_single_metric(
        dataframe,
        metric_id="metric_alpha",
        country_codes=["AAA", "BBB", "CCC"],
        forecast_year=2024,
        horizon_years=2,
        method=PredictionMethod.LAST_OBSERVED,
        fallback_method=None,
        comparison_options={
            "normalization_method": NormalizationMethod.MINMAX,
        },
    )

    # Independent composition oracle:
    #
    # Forecast:
    # AAA -> 10
    # BBB -> 20
    # CCC -> 30
    #
    # Min-max:
    # AAA -> 0.0
    # BBB -> 0.5
    # CCC -> 1.0
    #
    # Ranking:
    # CCC -> 1
    # BBB -> 2
    # AAA -> 3

    expected = {
        "AAA": (10.0, 0.0, 3),
        "BBB": (20.0, 0.5, 2),
        "CCC": (30.0, 1.0, 1),
    }

    assert result.selected_forecast_year == 2024
    assert result.selected_forecast_horizon == 1
    assert result.metadata["selection_mode"] == "forecast_year"
    assert result.metadata["comparison_target_year"] == 2024

    assert set(result.comparison_df["year"]) == {2024}

    for row in result.comparison_df.itertuples(index=False):
        expected_value, expected_normalized, expected_rank = expected[row.country_code]

        assert float(row.value) == pytest.approx(
            expected_value,
            abs=1e-12,
        )
        assert float(row.normalized_value) == pytest.approx(
            expected_normalized,
            abs=1e-12,
        )
        assert int(row.rank) == expected_rank


def test_pred_19_predicted_multi_metric_matches_independent_oracles() -> None:
    dataframe = _predicted_comparison_oracle_dataframe()

    result = compare_predicted_multi_metric(
        dataframe,
        metric_ids=["metric_alpha", "metric_beta"],
        country_codes=["AAA", "BBB", "CCC"],
        forecast_horizon=2,
        horizon_years=2,
        method=PredictionMethod.LAST_OBSERVED,
        fallback_method=None,
        comparison_options={
            "normalization_method": NormalizationMethod.MINMAX,
        },
    )

    # Horizon 2 from the common 2023 origin is 2025.
    assert result.selected_forecast_horizon == 2
    assert result.selected_forecast_year == 2025
    assert result.metadata["selection_mode"] == "forecast_horizon"

    # Independent oracles:
    #
    # metric_alpha, higher is better:
    #
    # AAA 10 -> 0.0 -> rank 3
    # BBB 20 -> 0.5 -> rank 2
    # CCC 30 -> 1.0 -> rank 1
    #
    # metric_beta, LOWER is better:
    #
    # AAA 30 -> 0.0 -> rank 3
    # BBB 10 -> 1.0 -> rank 1
    # CCC 20 -> 0.5 -> rank 2

    expected = {
        ("metric_alpha", "AAA"): (10.0, 0.0, 3),
        ("metric_alpha", "BBB"): (20.0, 0.5, 2),
        ("metric_alpha", "CCC"): (30.0, 1.0, 1),
        ("metric_beta", "AAA"): (30.0, 0.0, 3),
        ("metric_beta", "BBB"): (10.0, 1.0, 1),
        ("metric_beta", "CCC"): (20.0, 0.5, 2),
    }

    assert len(result.comparison_df) == 6

    for row in result.comparison_df.itertuples(index=False):
        expected_value, expected_normalized, expected_rank = expected[
            (row.metric_id, row.country_code)
        ]

        assert int(row.year) == 2025
        assert float(row.value) == pytest.approx(
            expected_value,
            abs=1e-12,
        )
        assert float(row.normalized_value) == pytest.approx(
            expected_normalized,
            abs=1e-12,
        )
        assert int(row.rank) == expected_rank


def test_pred_20_predicted_profile_matches_forecast_normalization_and_weight_oracle() -> (
    None
):
    dataframe = _predicted_comparison_oracle_dataframe()
    metrics_config, scoring_config = _predicted_profile_oracle_configs()

    result = compare_predicted_profile(
        dataframe,
        metrics_config=metrics_config,
        scoring_config=scoring_config,
        profile_name="oracle_profile",
        country_codes=["AAA", "BBB", "CCC"],
        forecast_horizon=1,
        horizon_years=2,
        method=PredictionMethod.LAST_OBSERVED,
        fallback_method=None,
    )

    # Forecast horizon 1:
    # selected year = 2024.
    #
    # metric_alpha normalized:
    # AAA=0.0, BBB=0.5, CCC=1.0
    #
    # metric_beta normalized, lower-is-better:
    # AAA=0.0, BBB=1.0, CCC=0.5
    #
    # weights:
    # alpha=0.6
    # beta=0.4
    #
    # AAA:
    #   0.0*0.6 + 0.0*0.4 = 0.0
    #
    # BBB:
    #   0.5*0.6 + 1.0*0.4
    #   = 0.3 + 0.4
    #   = 0.7
    #
    # CCC:
    #   1.0*0.6 + 0.5*0.4
    #   = 0.6 + 0.2
    #   = 0.8
    #
    # Final ranking:
    # CCC -> 1
    # BBB -> 2
    # AAA -> 3

    expected = {
        "AAA": (0.0, 3),
        "BBB": (0.7, 2),
        "CCC": (0.8, 1),
    }

    assert result.selected_forecast_horizon == 1
    assert result.selected_forecast_year == 2024

    assert list(result.comparison_df["country_code"]) == [
        "CCC",
        "BBB",
        "AAA",
    ]

    for row in result.comparison_df.itertuples(index=False):
        expected_score, expected_rank = expected[row.country_code]

        assert float(row.weighted_score) == pytest.approx(
            expected_score,
            abs=1e-12,
        )
        assert int(row.score_rank) == expected_rank

        assert int(row.metric_count_used) == 2
        assert int(row.metric_count_expected) == 2
        assert int(row.missing_metric_count) == 0
        assert float(row.weight_sum_used) == pytest.approx(
            1.0,
            abs=1e-12,
        )

        assert row.profile_name == "oracle_profile"


def test_pred_21_forecast_year_and_horizon_select_same_future_point() -> None:
    dataframe = _predicted_comparison_oracle_dataframe()

    by_year = compare_predicted_single_metric(
        dataframe,
        metric_id="metric_alpha",
        country_codes=["AAA", "BBB", "CCC"],
        forecast_year=2025,
        horizon_years=3,
        method=PredictionMethod.LAST_OBSERVED,
        fallback_method=None,
        comparison_options={
            "normalization_method": NormalizationMethod.MINMAX,
        },
    )

    by_horizon = compare_predicted_single_metric(
        dataframe,
        metric_id="metric_alpha",
        country_codes=["AAA", "BBB", "CCC"],
        forecast_horizon=2,
        horizon_years=3,
        method=PredictionMethod.LAST_OBSERVED,
        fallback_method=None,
        comparison_options={
            "normalization_method": NormalizationMethod.MINMAX,
        },
    )

    assert by_year.selected_forecast_year == 2025
    assert by_year.selected_forecast_horizon == 2
    assert by_year.metadata["selection_mode"] == "forecast_year"

    assert by_horizon.selected_forecast_year == 2025
    assert by_horizon.selected_forecast_horizon == 2
    assert by_horizon.metadata["selection_mode"] == "forecast_horizon"

    columns = [
        "country_code",
        "metric_id",
        "year",
        "value",
        "normalized_value",
        "rank",
    ]

    pd.testing.assert_frame_equal(
        by_year.comparison_df[columns].reset_index(drop=True),
        by_horizon.comparison_df[columns].reset_index(drop=True),
        check_dtype=True,
    )

    with pytest.raises(PredictionException) as exc_info:
        compare_predicted_single_metric(
            dataframe,
            metric_id="metric_alpha",
            country_codes=["AAA", "BBB", "CCC"],
            forecast_year=2025,
            forecast_horizon=2,
            horizon_years=3,
            method=PredictionMethod.LAST_OBSERVED,
            fallback_method=None,
        )

    exc = exc_info.value

    assert exc.code == PredictionErrorCode.INVALID_FORECAST_SELECTION
    assert exc.details == {
        "forecast_year": 2025,
        "forecast_horizon": 2,
    }
