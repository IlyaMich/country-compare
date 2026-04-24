from __future__ import annotations

import pandas as pd

from country_compare.prediction import build_forecast_table_dataframe
from country_compare.services import AppContext
from country_compare.services.prediction_service import PredictionService


class InMemoryDatasetService:
    def __init__(self, dataframe: pd.DataFrame) -> None:
        self.dataframe = dataframe

    def load_dataframe(self) -> pd.DataFrame:
        return self.dataframe.copy(deep=True)


def build_demo_df() -> pd.DataFrame:
    rows = []
    values = {
        ("ISR", "gdp_per_capita"): [30.0, 35.0, 40.0, 45.0, 50.0],
        ("FRA", "gdp_per_capita"): [28.0, 30.0, 32.0, 34.0, 36.0],
        ("ISR", "unemployment_pct"): [5.5, 5.2, 5.0, 4.8, 4.6],
        ("FRA", "unemployment_pct"): [8.8, 8.5, 8.2, 8.0, 7.8],
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
            rows.append(
                {
                    "country_code": country_code,
                    "country_name": country_names[country_code],
                    "metric_id": metric_id,
                    "metric_name": metric_name,
                    "value": value,
                    "year": 2018 + offset,
                    "unit": unit,
                    "source_name": "Demo Source",
                    "source_url": source_url,
                    "higher_is_better": higher_is_better,
                    "category": category,
                    "dataset_version": "phase-h-demo",
                    "region": "Demo Region",
                    "income_group": "High income",
                    "notes": None,
                }
            )

    return pd.DataFrame(rows)


def print_section(title: str) -> None:
    print("\n" + "=" * 100)
    print(title)
    print("=" * 100)


def main() -> None:
    canonical_df = build_demo_df()
    service = PredictionService(
        context=AppContext(),
        dataset_service=InMemoryDatasetService(canonical_df),
    )

    print_section("1) Method catalog")
    for method in service.list_prediction_methods():
        print(
            f"{method['method_id']}: {method['display_name']} — {method['description']}"
        )

    print_section("2) Single-country prediction using moving_average")
    single_result = service.run_single_metric_prediction(
        country_code="ISR",
        metric_id="gdp_per_capita",
        horizon_years=2,
        method="moving_average",
    )
    print("ok:", single_result.ok)
    print("summary:", single_result.summary)
    print(
        single_result.dataframe[
            ["country_code", "metric_id", "year", "value", "prediction_method"]
        ].to_string(index=False)
    )

    print_section("3) Multi-country forecast table for UI use")
    multi_result = service.run_single_metric_prediction_for_countries(
        metric_id="gdp_per_capita",
        country_codes=["ISR", "FRA"],
        horizon_years=2,
        method="moving_average",
    )
    forecast_table = build_forecast_table_dataframe(multi_result.prediction_result)
    print(
        forecast_table[
            [
                "country_code",
                "metric_id",
                "forecast_year",
                "forecast_horizon",
                "predicted_value",
                "prediction_method",
            ]
        ].to_string(index=False)
    )

    print_section("4) Predicted comparison for forecast horizon 1")
    comparison_result = service.run_predicted_single_metric_comparison(
        metric_id="gdp_per_capita",
        country_codes=["ISR", "FRA"],
        forecast_horizon=1,
        horizon_years=2,
        method="moving_average",
        comparison_options={"normalization_method": "minmax"},
    )
    print("ok:", comparison_result.ok)
    print(
        "selected_forecast_horizon:",
        comparison_result.summary["selected_forecast_horizon"],
    )
    print(
        comparison_result.dataframe[
            [
                "country_code",
                "country_name",
                "metric_id",
                "year",
                "value",
                "normalized_value",
                "rank",
            ]
        ].to_string(index=False)
    )

    print_section("5) Backtest summary")
    backtest_result = service.run_backtest(
        country_code="ISR",
        metric_id="gdp_per_capita",
        method="linear_trend",
        holdout_years=2,
    )
    print("ok:", backtest_result.ok)
    print("metrics:", backtest_result.summary["metrics"])
    print(
        backtest_result.dataframe[
            [
                "country_code",
                "metric_id",
                "year",
                "actual_value",
                "predicted_value",
                "error",
                "absolute_error",
            ]
        ].to_string(index=False)
    )

    print_section("6) Diagnostics summary")
    print(single_result.summary["diagnostics"])


if __name__ == "__main__":
    main()
