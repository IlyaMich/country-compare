from __future__ import annotations

import pandas as pd

from country_compare.prediction import (
    PredictionMethod,
    SingleMetricPredictionRequest,
    backtest_series,
    build_forecast_table_dataframe,
    predict_single_metric,
    predict_single_metric_for_countries,
)


def print_section(title: str) -> None:
    print("\n" + "=" * 100)
    print(title)
    print("=" * 100)


def make_demo_canonical_df() -> pd.DataFrame:
    rows = []
    values_by_country = {
        "ISR": ("Israel", [30.0, 35.0, 40.0, 45.0, 50.0]),
        "FRA": ("France", [28.0, 30.0, 32.0, 34.0, 36.0]),
    }
    for country_code, (country_name, values) in values_by_country.items():
        for offset, value in enumerate(values):
            rows.append(
                {
                    "country_code": country_code,
                    "country_name": country_name,
                    "metric_id": "gdp_per_capita",
                    "metric_name": "GDP per capita",
                    "value": value,
                    "year": 2018 + offset,
                    "unit": "USD",
                    "source_name": "Demo Source",
                    "source_url": "https://example.com/gdp",
                    "higher_is_better": True,
                    "category": "economy",
                    "dataset_version": "demo-v1",
                    "region": "Demo Region",
                    "income_group": "High income",
                    "notes": None,
                }
            )
    return pd.DataFrame(rows)


def show_frame(df: pd.DataFrame, columns: list[str] | None = None) -> None:
    if columns is not None:
        df = df.loc[:, [column for column in columns if column in df.columns]]
    if df.empty:
        print("<empty dataframe>")
        return
    print(df.to_string(index=False))


def main() -> None:
    canonical_df = make_demo_canonical_df()

    print_section("Input canonical demo data")
    show_frame(
        canonical_df,
        ["country_code", "country_name", "metric_id", "year", "value", "unit"],
    )

    print_section("Phase G single-series moving_average forecast")
    single_result = predict_single_metric(
        canonical_df,
        SingleMetricPredictionRequest(
            country_code="ISR",
            metric_id="gdp_per_capita",
            horizon_years=3,
            method=PredictionMethod.MOVING_AVERAGE,
        ),
    )
    show_frame(
        single_result.forecast_df,
        [
            "country_code",
            "metric_id",
            "year",
            "value",
            "forecast_horizon",
            "prediction_method",
            "diagnostic_status",
        ],
    )
    print("forecaster metadata:", single_result.forecaster_info[0].metadata)

    print_section("Phase G batch moving_average forecast table")
    batch_result = predict_single_metric_for_countries(
        canonical_df,
        metric_id="gdp_per_capita",
        country_codes=["ISR", "FRA"],
        horizon_years=2,
        method="moving_average",
    )
    show_frame(
        build_forecast_table_dataframe(batch_result),
        [
            "country_code",
            "country_name",
            "metric_id",
            "forecast_year",
            "forecast_horizon",
            "predicted_value",
            "prediction_method",
        ],
    )

    print_section("Phase G moving_average backtest")
    backtest_result = backtest_series(
        canonical_df,
        country_code="ISR",
        metric_id="gdp_per_capita",
        method=PredictionMethod.MOVING_AVERAGE,
        holdout_years=2,
    )
    show_frame(
        backtest_result.actual_vs_predicted_df,
        [
            "country_code",
            "metric_id",
            "year",
            "actual_value",
            "predicted_value",
            "error",
            "absolute_error",
            "forecast_horizon",
            "prediction_method",
        ],
    )
    print("metrics:", backtest_result.metrics)

    print_section("Expected interpretation")
    print(
        "moving_average uses the mean of the most recent 3 observations by default, "
        "or all available observations if there are only 2. The same flat value is "
        "used for every forecast horizon."
    )


if __name__ == "__main__":
    main()
