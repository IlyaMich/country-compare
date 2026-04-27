from __future__ import annotations

import pandas as pd

from country_compare.config.models import (
    MissingDataPolicy,
    NormalizationMethod,
    ScoringConfig,
    ScoringProfile,
    WeightHandlingStrategy,
    YearStrategy,
)
from country_compare.prediction import (
    compare_predicted_multi_metric,
    compare_predicted_profile,
    compare_predicted_single_metric,
    predict_metric_country_grid,
    predict_metrics_for_country,
    predict_single_metric_for_countries,
)


def _header(title: str) -> None:
    print()
    print("=" * 100)
    print(title)
    print("=" * 100)


def _build_demo_dataframe() -> pd.DataFrame:
    rows: list[dict[str, object]] = []

    series = {
        ("ISR", "gdp_per_capita"): [10.0, 20.0, 30.0],
        ("FRA", "gdp_per_capita"): [10.0, 15.0, 20.0],
        ("ISR", "unemployment_pct"): [8.0, 7.0, 6.0],
        ("FRA", "unemployment_pct"): [9.0, 8.5, 8.0],
    }

    country_names = {
        "ISR": "Israel",
        "FRA": "France",
    }

    metric_meta = {
        "gdp_per_capita": {
            "metric_name": "GDP per capita",
            "unit": "USD",
            "higher_is_better": True,
            "category": "economy",
            "source_url": "https://example.com/gdp",
        },
        "unemployment_pct": {
            "metric_name": "Unemployment",
            "unit": "pct",
            "higher_is_better": False,
            "category": "labor",
            "source_url": "https://example.com/unemployment",
        },
    }

    for (country_code, metric_id), values in series.items():
        for offset, value in enumerate(values):
            year = 2020 + offset
            meta = metric_meta[metric_id]
            rows.append(
                {
                    "country_code": country_code,
                    "country_name": country_names[country_code],
                    "metric_id": metric_id,
                    "metric_name": meta["metric_name"],
                    "value": value,
                    "year": year,
                    "unit": meta["unit"],
                    "source_name": "Example Source",
                    "source_url": meta["source_url"],
                    "higher_is_better": meta["higher_is_better"],
                    "category": meta["category"],
                    "dataset_version": "demo-v1",
                    "region": "Example Region",
                    "income_group": "High income",
                    "notes": None,
                }
            )

    return pd.DataFrame(rows)


def _build_demo_scoring_config() -> ScoringConfig:
    return ScoringConfig(
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


def main() -> None:
    canonical_df = _build_demo_dataframe()
    scoring_config = _build_demo_scoring_config()

    _header("1) Batch prediction: one metric across multiple countries")
    single_metric_batch = predict_single_metric_for_countries(
        canonical_df,
        metric_id="gdp_per_capita",
        country_codes=["ISR", "FRA"],
        horizon_years=2,
    )
    print(
        "successful_series_count:",
        single_metric_batch.metadata["successful_series_count"],
    )
    print("failed_series_count:", single_metric_batch.metadata["failed_series_count"])
    print(
        single_metric_batch.forecast_df[
            [
                "country_code",
                "metric_id",
                "year",
                "value",
                "forecast_horizon",
                "prediction_method",
                "prediction_run_id",
            ]
        ].to_string(index=False)
    )

    _header("2) Batch prediction: multiple metrics for one country")
    metrics_for_country = predict_metrics_for_country(
        canonical_df,
        country_code="ISR",
        metric_ids=["gdp_per_capita", "unemployment_pct"],
        horizon_years=1,
    )
    print(
        metrics_for_country.forecast_df[
            [
                "country_code",
                "metric_id",
                "year",
                "value",
                "forecast_horizon",
                "prediction_method",
            ]
        ].to_string(index=False)
    )

    _header("3) Batch prediction: full metric-country grid")
    grid_result = predict_metric_country_grid(
        canonical_df,
        country_codes=["ISR", "FRA"],
        metric_ids=["gdp_per_capita", "unemployment_pct"],
        horizon_years=1,
    )
    print("successful_series_count:", grid_result.metadata["successful_series_count"])
    print("comparison_ready rows:", len(grid_result.comparison_ready_df))
    print(
        grid_result.comparison_ready_df[
            [
                "country_code",
                "metric_id",
                "year",
                "value",
                "row_type",
                "is_predicted",
            ]
        ].to_string(index=False)
    )

    _header("4) Comparison bridge: predicted single-metric comparison by forecast year")
    single_metric_comparison = compare_predicted_single_metric(
        canonical_df,
        metric_id="gdp_per_capita",
        country_codes=["ISR", "FRA"],
        forecast_year=2023,
        horizon_years=2,
        comparison_options={"normalization_method": "minmax"},
    )
    print("selected_forecast_year:", single_metric_comparison.selected_forecast_year)
    print(
        single_metric_comparison.comparison_df[
            [
                "country_code",
                "metric_id",
                "year",
                "value",
                "normalized_value",
                "rank",
            ]
        ].to_string(index=False)
    )

    _header(
        "5) Comparison bridge: predicted multi-metric comparison by forecast horizon"
    )
    multi_metric_comparison = compare_predicted_multi_metric(
        canonical_df,
        metric_ids=["gdp_per_capita", "unemployment_pct"],
        country_codes=["ISR", "FRA"],
        forecast_horizon=1,
        horizon_years=2,
        comparison_options={"normalization_method": "minmax"},
    )
    print(
        "selected_forecast_horizon:", multi_metric_comparison.selected_forecast_horizon
    )
    print(
        multi_metric_comparison.comparison_df[
            [
                "country_code",
                "metric_id",
                "year",
                "value",
                "normalized_value",
                "rank",
            ]
        ].to_string(index=False)
    )

    _header("6) Comparison bridge: predicted profile comparison")
    profile_comparison = compare_predicted_profile(
        canonical_df,
        scoring_config=scoring_config,
        profile_name="economic_outlook",
        country_codes=["ISR", "FRA"],
        forecast_year=2023,
        horizon_years=1,
    )
    print("selected_forecast_year:", profile_comparison.selected_forecast_year)
    print(
        profile_comparison.comparison_df[
            [
                "country_code",
                "metric_id",
                "year",
                "value",
                "normalized_value",
                "rank",
            ]
        ].to_string(index=False)
    )

    _header("7) Partial failure path with fail_fast=False")
    partial_failure = predict_single_metric_for_countries(
        canonical_df,
        metric_id="gdp_per_capita",
        country_codes=["ISR", "USA", "FRA"],
        horizon_years=1,
        fail_fast=False,
    )
    print(
        "successful_series_count:", partial_failure.metadata["successful_series_count"]
    )
    print("failed_series_count:", partial_failure.metadata["failed_series_count"])
    for diagnostic in partial_failure.diagnostics:
        if diagnostic.status.value == "failed":
            error = diagnostic.errors[0]
            print(
                f"FAILED: country={diagnostic.country_code} metric={diagnostic.metric_id} "
                f"code={error.code.value} message={error.message}"
            )


if __name__ == "__main__":
    main()
