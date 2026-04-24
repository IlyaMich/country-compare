from country_compare.comparison.single_metric import compare_metric
from country_compare.config.models import (
    MetricConfig,
    MetricsConfig,
    NormalizationMethod,
)
from country_compare.data.examples import build_example_metric_dataframe


def build_metrics_config() -> MetricsConfig:
    return MetricsConfig(
        metrics={
            "gdp_per_capita": MetricConfig(
                display_name="GDP per capita",
                category="economy",
                higher_is_better=True,
                default_weight=1.0,
                unit="USD",
                normalization_method=NormalizationMethod.LOG_MINMAX,
            )
        }
    )


if __name__ == "__main__":
    df = build_example_metric_dataframe()

    selected = compare_metric(
        df,
        metric_id="gdp_per_capita",
        countries_include=["ISR", "DEU", "SGP"],
        normalization_method="minmax",
    )
    print("Selected countries, latest year:")
    print(selected[["country_code", "value", "normalized_value", "rank"]])
    print()

    target_year = compare_metric(
        df,
        metric_id="gdp_per_capita",
        year_strategy="target_year",
        target_year=2022,
        normalization_method="minmax",
    )
    print("Target year 2022:")
    print(target_year[["country_code", "year", "value", "normalized_value", "rank"]])
    print()

    config_driven = compare_metric(
        df,
        metric_id="gdp_per_capita",
        metrics_config=build_metrics_config(),
    )
    print("Config-driven normalization:")
    print(
        config_driven[
            [
                "country_code",
                "value",
                "normalization_method",
                "normalized_value",
                "rank",
            ]
        ]
    )
