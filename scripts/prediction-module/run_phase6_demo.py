from __future__ import annotations

import pandas as pd

from country_compare.prediction import PredictionMethod, backtest_series


def print_section(title: str) -> None:
    print("\n" + "=" * 100)
    print(title)
    print("=" * 100)


def make_demo_canonical_df() -> pd.DataFrame:
    rows = []
    values = [30.0, 35.0, 40.0, 45.0, 50.0]
    for offset, value in enumerate(values):
        rows.append(
            {
                "country_code": "ISR",
                "country_name": "Israel",
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

    print_section("Phase F backtest: latest 2 observed years as holdout")
    result = backtest_series(
        canonical_df,
        country_code="ISR",
        metric_id="gdp_per_capita",
        method=PredictionMethod.LINEAR_TREND,
        fallback_method=PredictionMethod.LAST_OBSERVED,
        holdout_years=2,
    )

    show_frame(
        result.actual_vs_predicted_df,
        [
            "country_code",
            "metric_id",
            "year",
            "actual_value",
            "predicted_value",
            "error",
            "absolute_error",
            "squared_error",
            "absolute_percentage_error",
            "forecast_horizon",
            "prediction_method",
        ],
    )

    print_section("Evaluation metrics")
    for key, value in result.metrics.items():
        print(f"{key}: {value}")

    print_section("Diagnostics")
    diagnostic = result.diagnostics[0]
    print(f"status: {diagnostic.status.value}")
    print(f"method_requested: {diagnostic.method_requested}")
    print(f"method_used: {diagnostic.method_used}")
    print(f"fallback_used: {diagnostic.fallback_used}")
    print(f"warnings: {diagnostic.warnings}")

    print_section("Expected interpretation")
    print(
        "The model trains only on 2018-2020, predicts held-out 2021-2022, "
        "then computes MAE/RMSE/MAPE from actual vs predicted values."
    )


if __name__ == "__main__":
    main()
