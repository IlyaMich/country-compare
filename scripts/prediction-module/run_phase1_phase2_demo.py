from __future__ import annotations

import pandas as pd

from country_compare.comparison.single_metric import compare_metric
from country_compare.config.models import YearStrategy
from country_compare.prediction import (
    PredictionException,
    PredictionMethod,
    SingleMetricPredictionRequest,
    predict_single_metric,
)


def make_demo_canonical_dataframe() -> pd.DataFrame:
    """Create a minimal canonical long-format dataset for the demo."""
    rows: list[dict] = []

    # Three countries with enough annual history for linear_trend.
    gdp_series = {
        "ISR": ("Israel", [2020, 2021, 2022], [42000.0, 45000.0, 48000.0]),
        "DEU": ("Germany", [2020, 2021, 2022], [50000.0, 51500.0, 53000.0]),
        "FRA": ("France", [2020, 2021, 2022], [46000.0, 47000.0, 47500.0]),
    }

    for country_code, (country_name, years, values) in gdp_series.items():
        for year, value in zip(years, values, strict=True):
            rows.append(
                {
                    "country_code": country_code,
                    "country_name": country_name,
                    "metric_id": "gdp_per_capita",
                    "metric_name": "GDP per capita",
                    "value": value,
                    "year": year,
                    "unit": "USD",
                    "source_name": "Demo Source",
                    "source_url": "https://example.com/demo-gdp",
                    "higher_is_better": True,
                    "category": "economy",
                    "dataset_version": "demo-v1",
                    "region": "Demo Region",
                    "income_group": "Demo Income Group",
                    "notes": "synthetic demo data",
                }
            )

    # Sparse two-observation metric for fallback demonstration.
    for year, value in [(2021, 6.0), (2022, 5.5)]:
        rows.append(
            {
                "country_code": "ISR",
                "country_name": "Israel",
                "metric_id": "unemployment_pct",
                "metric_name": "Unemployment",
                "value": value,
                "year": year,
                "unit": "%",
                "source_name": "Demo Source",
                "source_url": "https://example.com/demo-unemployment",
                "higher_is_better": False,
                "category": "economy",
                "dataset_version": "demo-v1",
                "region": "Demo Region",
                "income_group": "Demo Income Group",
                "notes": "synthetic sparse demo data",
            }
        )

    # Irregular annual history for missing-year warning demonstration.
    for year, value in [(2020, 80.0), (2022, 82.0), (2023, 83.0)]:
        rows.append(
            {
                "country_code": "ISR",
                "country_name": "Israel",
                "metric_id": "life_expectancy",
                "metric_name": "Life expectancy",
                "value": value,
                "year": year,
                "unit": "years",
                "source_name": "Demo Source",
                "source_url": "https://example.com/demo-life-expectancy",
                "higher_is_better": True,
                "category": "health",
                "dataset_version": "demo-v1",
                "region": "Demo Region",
                "income_group": "Demo Income Group",
                "notes": "synthetic irregular demo data",
            }
        )

    return pd.DataFrame(rows)


def print_section(title: str) -> None:
    print("\n" + "=" * 88)
    print(title)
    print("=" * 88)


def print_diagnostics(result) -> None:
    for diagnostic in result.diagnostics:
        print(
            {
                "status": diagnostic.status.value,
                "country_code": diagnostic.country_code,
                "metric_id": diagnostic.metric_id,
                "method_requested": diagnostic.method_requested,
                "method_used": diagnostic.method_used,
                "fallback_used": diagnostic.fallback_used,
                "history_observation_count": diagnostic.history_observation_count,
                "training_start_year": diagnostic.training_start_year,
                "training_end_year": diagnostic.training_end_year,
                "forecast_origin_year": diagnostic.forecast_origin_year,
                "missing_years": diagnostic.missing_years,
                "warnings": diagnostic.warnings,
                "errors": [error.message for error in diagnostic.errors],
            }
        )


def main() -> None:
    canonical_df = make_demo_canonical_dataframe()

    print_section("1) Demo canonical input")
    print(canonical_df.head(12).to_string(index=False))
    print(f"rows: {len(canonical_df)}")

    print_section("2) Single country + single metric forecast: default linear_trend")
    request = SingleMetricPredictionRequest(
        country_code="ISR",
        metric_id="gdp_per_capita",
        horizon_years=3,
        # method omitted intentionally; default should resolve to linear_trend.
    )
    result = predict_single_metric(canonical_df, request)

    print("metadata:")
    print(result.metadata)
    print("\ndiagnostics:")
    print_diagnostics(result)
    print("\nforecast_df:")
    print(
        result.forecast_df[
            [
                "country_code",
                "metric_id",
                "year",
                "value",
                "forecast_horizon",
                "prediction_method",
                "row_type",
                "is_predicted",
                "diagnostic_status",
            ]
        ].to_string(index=False)
    )

    print_section("3) Combined actual + predicted dataframe")
    print(
        result.combined_df[
            [
                "country_code",
                "metric_id",
                "year",
                "value",
                "row_type",
                "forecast_horizon",
                "prediction_method",
            ]
        ].to_string(index=False)
    )

    print_section("4) Explicit last_observed forecast")
    last_observed_result = predict_single_metric(
        canonical_df,
        SingleMetricPredictionRequest(
            country_code="ISR",
            metric_id="gdp_per_capita",
            horizon_years=3,
            method=PredictionMethod.LAST_OBSERVED,
        ),
    )
    print_diagnostics(last_observed_result)
    print(
        last_observed_result.forecast_df[
            ["country_code", "metric_id", "year", "value", "prediction_method"]
        ].to_string(index=False)
    )

    print_section("5) Fallback from linear_trend to last_observed for short history")
    fallback_result = predict_single_metric(
        canonical_df,
        SingleMetricPredictionRequest(
            country_code="ISR",
            metric_id="unemployment_pct",
            horizon_years=2,
            method=PredictionMethod.LINEAR_TREND,
            fallback_method=PredictionMethod.LAST_OBSERVED,
        ),
    )
    print_diagnostics(fallback_result)
    print(
        fallback_result.forecast_df[
            [
                "country_code",
                "metric_id",
                "year",
                "value",
                "prediction_method",
                "diagnostic_status",
                "diagnostic_messages",
            ]
        ].to_string(index=False)
    )

    print_section("6) Sparse/missing-year warning")
    sparse_result = predict_single_metric(
        canonical_df,
        SingleMetricPredictionRequest(
            country_code="ISR",
            metric_id="life_expectancy",
            horizon_years=2,
        ),
    )
    print_diagnostics(sparse_result)
    print(
        sparse_result.forecast_df[
            [
                "country_code",
                "metric_id",
                "year",
                "value",
                "prediction_method",
                "diagnostic_status",
                "diagnostic_messages",
            ]
        ].to_string(index=False)
    )

    print_section("7) Reuse existing comparison on canonical-like predicted rows")
    predicted_frames = []
    for country_code in ["ISR", "DEU", "FRA"]:
        country_result = predict_single_metric(
            canonical_df,
            SingleMetricPredictionRequest(
                country_code=country_code,
                metric_id="gdp_per_capita",
                horizon_years=2,
            ),
        )
        predicted_frames.append(country_result.comparison_ready_df)

    predicted_df = pd.concat(predicted_frames, ignore_index=True)
    forecast_year = 2024
    predicted_ranked = compare_metric(
        predicted_df,
        metric_id="gdp_per_capita",
        countries_include=["ISR", "DEU", "FRA"],
        year_strategy=YearStrategy.TARGET_YEAR,
        target_year=forecast_year,
        normalization_method="minmax",
    )

    print(f"Predicted comparison for forecast year {forecast_year}:")
    print(
        predicted_ranked[
            [
                "country_code",
                "country_name",
                "metric_id",
                "year",
                "value",
                "normalized_value",
                "rank",
                "prediction_method",
                "row_type",
            ]
        ].to_string(index=False)
    )

    print_section("8) Expected structured error example: invalid horizon")
    try:
        predict_single_metric(
            canonical_df,
            SingleMetricPredictionRequest(
                country_code="ISR",
                metric_id="gdp_per_capita",
                horizon_years=0,
            ),
        )
    except PredictionException as exc:
        print("caught PredictionException:")
        print(
            {
                "code": exc.code.value,
                "message": exc.message,
                "country_code": exc.country_code,
                "metric_id": exc.metric_id,
                "details": exc.details,
            }
        )

    print_section("Demo complete")


if __name__ == "__main__":
    main()
