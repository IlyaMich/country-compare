from __future__ import annotations

import pandas as pd
import pytest

from country_compare.config.models import (
    MissingDataPolicy,
    NormalizationMethod,
    ScoringConfig,
    ScoringProfile,
    WeightHandlingStrategy,
    YearStrategy,
)
from country_compare.data.contract import REQUIRED_COLUMNS
from country_compare.prediction import (
    PredictionDiagnosticStatus,
    PredictionErrorCode,
    PredictionException,
    compare_predicted_multi_metric,
    compare_predicted_profile,
    compare_predicted_single_metric,
    predict_metric_country_grid,
    predict_metrics_for_country,
    predict_single_metric_for_countries,
)
from country_compare.prediction.output import PREDICTION_METADATA_COLUMNS


def _canonical_df() -> pd.DataFrame:
    rows = []
    values = {
        ("ISR", "gdp_per_capita"): [10.0, 20.0, 30.0],
        ("FRA", "gdp_per_capita"): [10.0, 15.0, 20.0],
        ("ISR", "unemployment_pct"): [8.0, 7.0, 6.0],
        ("FRA", "unemployment_pct"): [9.0, 8.5, 8.0],
    }
    country_names = {"ISR": "Israel", "FRA": "France"}
    metric_meta = {
        "gdp_per_capita": (
            "GDP per capita",
            "USD",
            True,
            "economy",
            "https://example.com/gdp",
        ),
        "unemployment_pct": (
            "Unemployment",
            "pct",
            False,
            "labor",
            "https://example.com/unemployment",
        ),
    }
    for (country_code, metric_id), series in values.items():
        metric_name, unit, higher_is_better, category, source_url = metric_meta[
            metric_id
        ]
        for offset, value in enumerate(series):
            year = 2020 + offset
            rows.append(
                {
                    "country_code": country_code,
                    "country_name": country_names[country_code],
                    "metric_id": metric_id,
                    "metric_name": metric_name,
                    "value": value,
                    "year": year,
                    "unit": unit,
                    "source_name": "Example Source",
                    "source_url": source_url,
                    "higher_is_better": higher_is_better,
                    "category": category,
                    "dataset_version": "test-v1",
                    "region": "Example Region",
                    "income_group": "High income",
                    "notes": None,
                }
            )
    return pd.DataFrame(rows)


def test_predict_single_metric_for_countries_succeeds() -> None:
    result = predict_single_metric_for_countries(
        _canonical_df(),
        metric_id="gdp_per_capita",
        country_codes=["ISR", "FRA", "ISR"],
        horizon_years=2,
    )

    assert result.metadata["successful_series_count"] == 2
    assert result.metadata["failed_series_count"] == 0
    assert result.forecast_df["country_code"].tolist() == ["ISR", "ISR", "FRA", "FRA"]
    assert result.forecast_df["year"].tolist() == [2023, 2024, 2023, 2024]
    assert result.forecast_df["prediction_run_id"].nunique() == 1


def test_predict_metrics_for_country_succeeds() -> None:
    result = predict_metrics_for_country(
        _canonical_df(),
        country_code="ISR",
        metric_ids=["gdp_per_capita", "unemployment_pct"],
        horizon_years=1,
    )

    assert result.metadata["successful_series_count"] == 2
    assert sorted(result.forecast_df["metric_id"].unique().tolist()) == [
        "gdp_per_capita",
        "unemployment_pct",
    ]
    assert result.combined_df["row_type"].tolist().count("actual") == 6
    assert result.combined_df["row_type"].tolist().count("predicted") == 2


def test_predict_metric_country_grid_succeeds() -> None:
    result = predict_metric_country_grid(
        _canonical_df(),
        country_codes=["ISR", "FRA"],
        metric_ids=["gdp_per_capita", "unemployment_pct"],
        horizon_years=1,
    )

    assert result.metadata["successful_series_count"] == 4
    assert len(result.forecast_df) == 4
    assert len(result.comparison_ready_df) == 4
    assert result.forecast_df["prediction_run_id"].nunique() == 1


def test_partial_failure_with_fail_fast_false_records_diagnostics_and_keeps_successes() -> (
    None
):
    result = predict_single_metric_for_countries(
        _canonical_df(),
        metric_id="gdp_per_capita",
        country_codes=["ISR", "USA", "FRA"],
        horizon_years=1,
        fail_fast=False,
    )

    assert result.metadata["successful_series_count"] == 2
    assert result.metadata["failed_series_count"] == 1
    assert set(result.forecast_df["country_code"].unique().tolist()) == {"ISR", "FRA"}
    failed = [
        d for d in result.diagnostics if d.status == PredictionDiagnosticStatus.FAILED
    ]
    assert len(failed) == 1
    assert failed[0].errors[0].code == PredictionErrorCode.MISSING_COUNTRY


def test_fail_fast_true_raises_on_first_failed_series() -> None:
    with pytest.raises(PredictionException) as exc_info:
        predict_single_metric_for_countries(
            _canonical_df(),
            metric_id="gdp_per_capita",
            country_codes=["USA", "ISR"],
            horizon_years=1,
            fail_fast=True,
        )

    assert exc_info.value.code == PredictionErrorCode.MISSING_COUNTRY


def test_empty_country_selection_is_invalid() -> None:
    with pytest.raises(PredictionException) as exc_info:
        predict_single_metric_for_countries(
            _canonical_df(),
            metric_id="gdp_per_capita",
            country_codes=[],
            horizon_years=1,
        )

    assert exc_info.value.code == PredictionErrorCode.EMPTY_COUNTRY_SELECTION


def test_empty_metric_selection_is_invalid() -> None:
    with pytest.raises(PredictionException) as exc_info:
        predict_metric_country_grid(
            _canonical_df(),
            country_codes=["ISR"],
            metric_ids=[],
            horizon_years=1,
        )

    assert exc_info.value.code == PredictionErrorCode.EMPTY_METRIC_SELECTION


def test_batch_output_preserves_canonical_and_prediction_metadata_columns() -> None:
    result = predict_metric_country_grid(
        _canonical_df(),
        country_codes=["ISR", "FRA"],
        metric_ids=["gdp_per_capita", "unemployment_pct"],
        horizon_years=1,
    )

    for column in REQUIRED_COLUMNS:
        assert column in result.forecast_df.columns
    for column in PREDICTION_METADATA_COLUMNS:
        assert column in result.forecast_df.columns
    assert result.comparison_ready_df["row_type"].eq("predicted").all()
    assert (
        result.comparison_ready_df.duplicated(
            subset=["country_code", "metric_id", "year"]
        ).sum()
        == 0
    )


def test_predicted_single_metric_comparison_ranks_countries_for_selected_forecast_year() -> (
    None
):
    result = compare_predicted_single_metric(
        _canonical_df(),
        metric_id="gdp_per_capita",
        country_codes=["ISR", "FRA"],
        forecast_year=2023,
        horizon_years=2,
        comparison_options={"normalization_method": "minmax"},
    )

    assert result.selected_forecast_year == 2023
    assert result.comparison_df["country_code"].tolist() == ["ISR", "FRA"]
    assert result.comparison_df["rank"].tolist() == [1, 2]


def test_predicted_single_metric_comparison_works_when_selecting_by_forecast_horizon() -> (
    None
):
    result = compare_predicted_single_metric(
        _canonical_df(),
        metric_id="gdp_per_capita",
        country_codes=["ISR", "FRA"],
        forecast_horizon=2,
        horizon_years=2,
        comparison_options={"normalization_method": "rank"},
    )

    assert result.selected_forecast_horizon == 2
    assert result.comparison_df["rank"].tolist() == [1, 2]
    assert result.comparison_df["normalization_method"].eq("rank").all()


def test_predicted_multi_metric_comparison_works_for_selected_forecast_year() -> None:
    result = compare_predicted_multi_metric(
        _canonical_df(),
        metric_ids=["gdp_per_capita", "unemployment_pct"],
        country_codes=["ISR", "FRA"],
        forecast_year=2023,
        horizon_years=2,
        comparison_options={"normalization_method": NormalizationMethod.MINMAX},
    )

    assert result.selected_forecast_year == 2023
    assert set(result.comparison_df["metric_id"].unique().tolist()) == {
        "gdp_per_capita",
        "unemployment_pct",
    }
    gdp_rows = result.comparison_df.loc[
        result.comparison_df["metric_id"].eq("gdp_per_capita")
    ]
    unemployment_rows = result.comparison_df.loc[
        result.comparison_df["metric_id"].eq("unemployment_pct")
    ]
    assert gdp_rows.iloc[0]["country_code"] == "ISR"
    assert unemployment_rows.iloc[0]["country_code"] == "ISR"


def test_invalid_forecast_selection_raises_structured_error() -> None:
    with pytest.raises(PredictionException) as exc_info:
        compare_predicted_single_metric(
            _canonical_df(),
            metric_id="gdp_per_capita",
            country_codes=["ISR", "FRA"],
            forecast_year=2023,
            forecast_horizon=1,
            horizon_years=2,
        )

    assert exc_info.value.code == PredictionErrorCode.INVALID_FORECAST_SELECTION


def test_bridge_output_includes_prediction_diagnostics() -> None:
    result = compare_predicted_single_metric(
        _canonical_df(),
        metric_id="gdp_per_capita",
        country_codes=["ISR", "USA", "FRA"],
        forecast_year=2023,
        horizon_years=1,
        comparison_options={"normalization_method": "minmax"},
    )

    assert any(
        d.status == PredictionDiagnosticStatus.FAILED for d in result.diagnostics
    )
    assert result.prediction_result.metadata["failed_series_count"] == 1


def test_compare_predicted_profile_is_straightforward_with_existing_scoring_config() -> (
    None
):
    scoring_config = ScoringConfig(
        default_profile="economic_outlook",
        weight_handling=WeightHandlingStrategy.NORMALIZE,
        default_year_strategy=YearStrategy.LATEST_PER_METRIC,
        default_missing_data_policy=MissingDataPolicy.RENORMALIZE_WEIGHTS,
        profiles={
            "economic_outlook": ScoringProfile(
                metrics=["gdp_per_capita", "unemployment_pct"],
                normalization_overrides={
                    "gdp_per_capita": NormalizationMethod.MINMAX,
                    "unemployment_pct": NormalizationMethod.MINMAX,
                },
            )
        },
    )

    result = compare_predicted_profile(
        _canonical_df(),
        scoring_config=scoring_config,
        profile_name="economic_outlook",
        country_codes=["ISR", "FRA"],
        forecast_year=2023,
        horizon_years=1,
    )

    assert result.selected_forecast_year == 2023
    assert set(result.comparison_df["metric_id"].unique().tolist()) == {
        "gdp_per_capita",
        "unemployment_pct",
    }
