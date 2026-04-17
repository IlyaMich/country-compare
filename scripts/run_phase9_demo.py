from country_compare.config.models import (
    MetricConfig,
    MetricsConfig,
    MissingDataPolicy,
    NormalizationMethod,
    ScoringConfig,
    ScoringProfile,
    WeightHandlingStrategy,
    YearStrategy,
)
from country_compare.data.examples import build_example_metric_dataframe
from country_compare.scoring.weighted_score import score_countries


def build_metrics_config() -> MetricsConfig:
    return MetricsConfig(
        metrics={
            "gdp_per_capita": MetricConfig(
                display_name="GDP per capita",
                category="economy",
                higher_is_better=True,
                default_weight=2.0,
                unit="USD",
                normalization_method=NormalizationMethod.MINMAX,
            ),
            "rule_of_law": MetricConfig(
                display_name="Rule of Law",
                category="governance",
                higher_is_better=True,
                default_weight=1.0,
                unit="index",
                normalization_method=NormalizationMethod.MINMAX,
            ),
        }
    )


def build_scoring_config() -> ScoringConfig:
    return ScoringConfig(
        default_profile="core",
        weight_handling=WeightHandlingStrategy.NORMALIZE,
        default_year_strategy=YearStrategy.COMMON_YEAR,
        default_missing_data_policy=MissingDataPolicy.RENORMALIZE_WEIGHTS,
        profiles={
            "core": ScoringProfile(
                metrics=["gdp_per_capita", "rule_of_law"],
                weights={"gdp_per_capita": 3.0, "rule_of_law": 1.0},
                normalization_overrides={
                    "gdp_per_capita": NormalizationMethod.MINMAX,
                    "rule_of_law": NormalizationMethod.MINMAX,
                },
                year_strategy=YearStrategy.COMMON_YEAR,
                missing_data_policy=MissingDataPolicy.RENORMALIZE_WEIGHTS,
            )
        },
    )


if __name__ == "__main__":
    df = build_example_metric_dataframe()
    scored = score_countries(
        df,
        metrics_config=build_metrics_config(),
        scoring_config=build_scoring_config(),
        profile_name="core",
    )
    print(scored)
