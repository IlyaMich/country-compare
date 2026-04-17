from country_compare.data.examples import build_example_metric_dataframe
from country_compare.config.models import YearStrategy
from country_compare.metrics.filtering import (
    filter_countries,
    filter_metrics,
    apply_year_strategy,
    filter_dataset,
)

import pandas as pd


def print_section(title: str, df: pd.DataFrame):
    print("\n" + "=" * 80)
    print(title)
    print("=" * 80)
    print(df.sort_values(["country_code", "metric_id", "year"]).to_string(index=False))


def main():
    # Load example dataset (Phase 2)
    df = build_example_metric_dataframe()

    print_section("FULL DATASET", df)

    # --------------------------------------------------
    # 1. Filter Countries
    # --------------------------------------------------
    df_countries = filter_countries(df, include=["ISR", "DEU"])
    print_section("FILTER: Countries = ISR, DEU", df_countries)

    # --------------------------------------------------
    # 2. Filter Metrics
    # --------------------------------------------------
    df_metrics = filter_metrics(df, include=["gdp_per_capita"])
    print_section("FILTER: Metric = gdp_per_capita", df_metrics)

    # --------------------------------------------------
    # 3. Latest per Metric
    # --------------------------------------------------
    df_latest = apply_year_strategy(df, YearStrategy.LATEST_PER_METRIC)
    print_section("YEAR STRATEGY: latest_per_metric", df_latest)

    # --------------------------------------------------
    # 4. Target Year
    # --------------------------------------------------
    df_2022 = apply_year_strategy(df, YearStrategy.TARGET_YEAR, target_year=2022)
    print_section("YEAR STRATEGY: target_year = 2022", df_2022)

    # --------------------------------------------------
    # 5. Common Year
    # --------------------------------------------------
    df_common = apply_year_strategy(df, YearStrategy.COMMON_YEAR)
    print_section("YEAR STRATEGY: common_year", df_common)

    # --------------------------------------------------
    # 6. Full Pipeline (what you'll actually use later)
    # --------------------------------------------------
    df_pipeline = filter_dataset(
        df,
        countries_include=["ISR", "DEU", "SGP"],
        metrics_include=["gdp_per_capita", "rule_of_law"],
        year_strategy=YearStrategy.COMMON_YEAR,
    )

    print_section(
        "PIPELINE: Countries + Metrics + common_year",
        df_pipeline,
    )


if __name__ == "__main__":
    main()