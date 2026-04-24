from __future__ import annotations

import pandas as pd

from country_compare.prediction import (
    build_actual_vs_predicted_dataframe,
    build_forecast_table_dataframe,
    build_line_chart_dataframe,
    predict_metric_country_grid,
    predict_single_metric,
    predict_single_metric_for_countries,
)
from country_compare.prediction.models import PredictionMethod, SingleMetricPredictionRequest


def print_section(title: str) -> None:
    print("\n" + "=" * 100)
    print(title)
    print("=" * 100)


def make_demo_canonical_df() -> pd.DataFrame:
    rows = []

    values = {
        ("ISR", "Israel", "gdp_per_capita"): [30.0, 35.0, 40.0],
        ("FRA", "France", "gdp_per_capita"): [20.0, 22.5, 25.0],
        ("ISR", "Israel", "unemployment_pct"): [6.0, 5.5, 5.0],
        ("FRA", "France", "unemployment_pct"): [8.0, 7.8, 7.5],
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

    for (country_code, country_name, metric_id), series in values.items():
        meta = metric_meta[metric_id]
        for offset, value in enumerate(series):
            rows.append(
                {
                    "country_code": country_code,
                    "country_name": country_name,
                    "metric_id": metric_id,
                    "metric_name": meta["metric_name"],
                    "value": value,
                    "year": 2020 + offset,
                    "unit": meta["unit"],
                    "source_name": "Demo Source",
                    "source_url": meta["source_url"],
                    "higher_is_better": meta["higher_is_better"],
                    "category": meta["category"],
                    "dataset_version": "demo-v1",
                    "region": "Demo Region",
                    "income_group": "High income",
                    "notes": None,
                }
            )

    return pd.DataFrame(rows)


def show_frame(df: pd.DataFrame, columns: list[str] | None = None, max_rows: int = 20) -> None:
    if columns is not None:
        existing_columns = [column for column in columns if column in df.columns]
        df = df.loc[:, existing_columns]

    if df.empty:
        print("<empty dataframe>")
        return

    print(df.head(max_rows).to_string(index=False))


def main() -> None:
    canonical_df = make_demo_canonical_df()

    print_section("Input canonical demo data")
    show_frame(
        canonical_df,
        [
            "country_code",
            "country_name",
            "metric_id",
            "metric_name",
            "year",
            "value",
            "unit",
            "higher_is_better",
        ],
    )

    print_section("1) Single country + single metric: line chart dataframe")
    single_result = predict_single_metric(
        canonical_df,
        SingleMetricPredictionRequest(
            country_code="ISR",
            metric_id="gdp_per_capita",
            horizon_years=2,
            method=PredictionMethod.LINEAR_TREND,
        ),
    )
    single_line_df = build_line_chart_dataframe(single_result)
    show_frame(
        single_line_df,
        [
            "country_code",
            "country_name",
            "metric_id",
            "metric_name",
            "year",
            "value",
            "row_type",
            "series_label",
            "overlay_series_label",
            "prediction_method",
            "forecast_horizon",
        ],
    )

    print_section("2) Same result: actual-vs-predicted overlay dataframe")
    overlay_df = build_actual_vs_predicted_dataframe(single_result)
    show_frame(
        overlay_df,
        [
            "country_code",
            "country_name",
            "metric_id",
            "metric_name",
            "year",
            "value",
            "row_type",
            "series_label",
            "overlay_series_label",
            "prediction_method",
            "forecast_horizon",
        ],
    )

    print_section("3) Same result: forecast-only table dataframe")
    forecast_table_df = build_forecast_table_dataframe(single_result)
    show_frame(
        forecast_table_df,
        [
            "country_code",
            "country_name",
            "metric_id",
            "metric_name",
            "forecast_year",
            "forecast_horizon",
            "predicted_value",
            "unit",
            "prediction_method",
            "forecast_origin_year",
            "diagnostic_status",
        ],
    )

    print_section("4) One metric across multiple countries: chart dataframe")
    multi_country_result = predict_single_metric_for_countries(
        canonical_df,
        metric_id="gdp_per_capita",
        country_codes=["ISR", "FRA"],
        horizon_years=2,
        method=PredictionMethod.LINEAR_TREND,
    )
    multi_country_line_df = build_line_chart_dataframe(multi_country_result)
    show_frame(
        multi_country_line_df,
        [
            "country_code",
            "country_name",
            "metric_id",
            "year",
            "value",
            "row_type",
            "series_label",
            "overlay_series_label",
            "forecast_horizon",
        ],
    )

    print_section("5) Country/metric grid: chart dataframe")
    grid_result = predict_metric_country_grid(
        canonical_df,
        country_codes=["ISR", "FRA"],
        metric_ids=["gdp_per_capita", "unemployment_pct"],
        horizon_years=1,
        method=PredictionMethod.LINEAR_TREND,
    )
    grid_line_df = build_line_chart_dataframe(grid_result)
    show_frame(
        grid_line_df,
        [
            "country_code",
            "country_name",
            "metric_id",
            "metric_name",
            "year",
            "value",
            "row_type",
            "series_label",
            "overlay_series_label",
            "forecast_horizon",
        ],
        max_rows=30,
    )

    print_section("6) Grid forecast-only table")
    grid_forecast_table_df = build_forecast_table_dataframe(grid_result)
    show_frame(
        grid_forecast_table_df,
        [
            "country_code",
            "country_name",
            "metric_id",
            "metric_name",
            "forecast_year",
            "forecast_horizon",
            "predicted_value",
            "unit",
            "prediction_method",
            "diagnostic_status",
        ],
    )

    print_section("7) Basic shape checks")
    print(f"single line rows: {len(single_line_df)}")
    print(f"single forecast table rows: {len(forecast_table_df)}")
    print(f"multi-country line rows: {len(multi_country_line_df)}")
    print(f"grid line rows: {len(grid_line_df)}")
    print(f"grid forecast table rows: {len(grid_forecast_table_df)}")
    print(f"grid successful_series_count: {grid_result.metadata.get('successful_series_count')}")
    print(f"grid failed_series_count: {grid_result.metadata.get('failed_series_count')}")

    print_section("Expected interpretation")
    print(
        "The Phase E helpers should not change prediction values. They only reshape existing "
        "PredictionResult dataframes into renderer-neutral tables with labels such as "
        "series_label, overlay_series_label, forecast_year, and predicted_value."
    )


if __name__ == "__main__":
    main()
