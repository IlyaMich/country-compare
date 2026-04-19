from country_compare.comparison.multi_metric import (
    build_multi_metric_wide_table,
    compare_countries,
)
from country_compare.config.models import MetricConfig, MetricsConfig, NormalizationMethod
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
            ),
            "rule_of_law": MetricConfig(
                display_name="Rule of Law",
                category="governance",
                higher_is_better=True,
                default_weight=1.0,
                unit="index",
                normalization_method=NormalizationMethod.PERCENTILE,
            ),
        }
    )


if __name__ == "__main__":
    df = build_example_metric_dataframe()

    long_result = compare_countries(
        df,
        metric_ids=["gdp_per_capita", "rule_of_law"],
        metrics_config=build_metrics_config(),
    )
    print("Long multi-metric comparison:")
    print(
        long_result[
            [
                "metric_id",
                "country_code",
                "year",
                "value",
                "normalization_method",
                "normalized_value",
                "rank",
            ]
        ]
    )
    print()

    wide_result = build_multi_metric_wide_table(long_result)
    print("Wide comparison table:")
    print(wide_result)
