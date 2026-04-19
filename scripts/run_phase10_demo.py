from __future__ import annotations

import inspect
from pathlib import Path

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
from country_compare.output import (
    make_single_metric_table,
    make_weighted_score_table,
    plot_single_metric_ranking,
    plot_weighted_scores,
)

# These imports assume your Phase 7 and Phase 9 modules already exist in the repo.
from country_compare.comparison.single_metric import compare_metric
from country_compare.scoring.weighted_score import score_countries


OUTPUT_DIR = Path("phase10_output_examples")
OUTPUT_DIR.mkdir(exist_ok=True)



def build_example_configs() -> tuple[MetricsConfig, ScoringConfig]:
    metrics_config = MetricsConfig(
        metrics={
            "gdp_per_capita": MetricConfig(
                display_name="GDP per capita",
                category="economy",
                higher_is_better=True,
                default_weight=0.5,
                unit="USD",
                normalization_method=NormalizationMethod.MINMAX,
            ),
            "rule_of_law": MetricConfig(
                display_name="Rule of Law",
                category="governance",
                higher_is_better=True,
                default_weight=0.3,
                unit="index",
                normalization_method=NormalizationMethod.MINMAX,
            ),
            "democracy_index": MetricConfig(
                display_name="Democracy Index",
                category="governance",
                higher_is_better=True,
                default_weight=0.2,
                unit="score_0_10",
                normalization_method=NormalizationMethod.MINMAX,
            ),
        }
    )

    scoring_config = ScoringConfig(
        default_profile="default",
        weight_handling=WeightHandlingStrategy.NORMALIZE,
        default_year_strategy=YearStrategy.LATEST_PER_METRIC,
        default_missing_data_policy=MissingDataPolicy.RENORMALIZE_WEIGHTS,
        profiles={
            "default": ScoringProfile(
                metrics=["gdp_per_capita", "rule_of_law", "democracy_index"],
                weights={
                    "gdp_per_capita": 0.5,
                    "rule_of_law": 0.3,
                    "democracy_index": 0.2,
                },
                year_strategy=YearStrategy.LATEST_PER_METRIC,
                missing_data_policy=MissingDataPolicy.RENORMALIZE_WEIGHTS,
            )
        },
    )

    return metrics_config, scoring_config



def invoke_with_supported_kwargs(func, **kwargs):
    signature = inspect.signature(func)
    accepted_kwargs = {}

    for name, parameter in signature.parameters.items():
        if parameter.kind == inspect.Parameter.VAR_KEYWORD:
            accepted_kwargs.update(kwargs)
            break
        if name in kwargs:
            accepted_kwargs[name] = kwargs[name]

    return func(**accepted_kwargs)



def build_single_metric_result(data, metrics_config, scoring_config):
    countries = ["ISR", "DEU", "SGP"]

    try:
        return invoke_with_supported_kwargs(
            compare_metric,
            df=data,
            dataframe=data,
            data=data,
            metric_id="gdp_per_capita",
            countries=countries,
            country_codes=countries,
            metrics_config=metrics_config,
            scoring_config=scoring_config,
            profile_name="default",
            method="minmax",
            normalization_method="minmax",
            year_strategy=YearStrategy.LATEST_PER_METRIC.value,
            target_year=None,
        )
    except TypeError as exc:
        raise RuntimeError(
            "Could not call compare_metric(...) with the adaptive example wrapper. "
            "Please align the example call with your exact Phase 7 signature."
        ) from exc



def build_weighted_score_result(data, metrics_config, scoring_config):
    countries = ["ISR", "DEU", "SGP"]

    try:
        return invoke_with_supported_kwargs(
            score_countries,
            df=data,
            dataframe=data,
            data=data,
            countries=countries,
            country_codes=countries,
            metrics_config=metrics_config,
            scoring_config=scoring_config,
            profile_name="default",
            year_strategy=YearStrategy.LATEST_PER_METRIC.value,
            missing_data_policy=MissingDataPolicy.RENORMALIZE_WEIGHTS.value,
        )
    except TypeError as exc:
        raise RuntimeError(
            "Could not call score_countries(...) with the adaptive example wrapper. "
            "Please align the example call with your exact Phase 9 signature."
        ) from exc



def main() -> None:
    data = build_example_metric_dataframe()
    metrics_config, scoring_config = build_example_configs()

    single_metric_result = build_single_metric_result(data, metrics_config, scoring_config)
    single_metric_table = make_single_metric_table(
        single_metric_result,
        rename_columns={"country_name": "country"},
        round_ndigits={"value": 0, "normalized_value": 3},
    )
    print("\n=== Single Metric Table ===")
    print(single_metric_table.to_string(index=False))

    single_fig, _ = plot_single_metric_ranking(
        single_metric_result,
        title="GDP per Capita Ranking",
    )
    single_fig.savefig(OUTPUT_DIR / "single_metric_ranking.png", bbox_inches="tight")

    weighted_score_result = build_weighted_score_result(data, metrics_config, scoring_config)
    weighted_score_table = make_weighted_score_table(
        weighted_score_result,
        rename_columns={"country_name": "country"},
        round_ndigits={"weighted_score": 3, "weight_sum_used": 3},
    )
    print("\n=== Weighted Score Table ===")
    print(weighted_score_table.to_string(index=False))

    score_fig, _ = plot_weighted_scores(
        weighted_score_result,
        title="Weighted Country Scores",
    )
    score_fig.savefig(OUTPUT_DIR / "weighted_scores.png", bbox_inches="tight")

    print(f"\nSaved charts to: {OUTPUT_DIR.resolve()}")


if __name__ == "__main__":
    main()
