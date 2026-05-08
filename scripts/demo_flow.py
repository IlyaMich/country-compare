from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from country_compare.comparison.multi_metric import compare_countries
from country_compare.comparison.single_metric import compare_metric
from country_compare.config.loader import load_metrics_config, load_scoring_config
from country_compare.config.models import YearStrategy
from country_compare.data.validation import validate_and_parse_dataframe
from country_compare.exports import (
    export_diagnostics_json,
    export_markdown_summary,
    export_tables_csv,
)
from country_compare.prediction.comparison_bridge import compare_predicted_single_metric
from country_compare.prediction.multi_metric import predict_single_metric_for_countries
from country_compare.prediction.visualization import build_forecast_table_dataframe
from country_compare.scoring.weighted_score import score_countries

COUNTRIES = ["ISR", "FRA", "DEU", "SGP"]
SINGLE_METRIC_ID = "gdp_per_capita"
PROFILE_NAME = "balanced_demo"


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run the deterministic Country Compare golden demo flow."
    )
    parser.add_argument(
        "--data-path",
        default="data/examples/golden_demo_metrics.csv",
        help="Path to the golden demo canonical CSV dataset.",
    )
    parser.add_argument(
        "--metrics-config",
        default="config/metrics_test.yaml",
        help="Path to the demo metrics config.",
    )
    parser.add_argument(
        "--scoring-config",
        default="config/scoring_profiles_test.yaml",
        help="Path to the demo scoring profile config.",
    )
    parser.add_argument(
        "--output-dir",
        default="data/exports/golden_demo",
        help="Directory where demo result files will be written.",
    )
    args = parser.parse_args()

    data_path = Path(args.data_path)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    canonical_df = pd.read_csv(data_path)
    validate_and_parse_dataframe(canonical_df)

    metrics_config = load_metrics_config(args.metrics_config)
    scoring_config = load_scoring_config(args.scoring_config)

    single_metric_df = compare_metric(
        canonical_df,
        metric_id=SINGLE_METRIC_ID,
        countries_include=COUNTRIES,
        year_strategy=YearStrategy.COMMON_YEAR,
        metrics_config=metrics_config,
    )

    multi_metric_df = compare_countries(
        canonical_df,
        metric_ids=[
            "gdp_per_capita",
            "life_expectancy",
            "unemployment_pct",
            "governance_score",
        ],
        countries_include=COUNTRIES,
        year_strategy=YearStrategy.COMMON_YEAR,
        metrics_config=metrics_config,
    )

    weighted_score_df = score_countries(
        canonical_df,
        metrics_config=metrics_config,
        scoring_config=scoring_config,
        profile_name=PROFILE_NAME,
        countries_include=COUNTRIES,
    )

    prediction_result = predict_single_metric_for_countries(
        canonical_df,
        metric_id=SINGLE_METRIC_ID,
        country_codes=COUNTRIES,
        horizon_years=2,
        method="linear_trend",
        fallback_method="last_observed",
    )
    forecast_table_df = build_forecast_table_dataframe(prediction_result)

    predicted_comparison = compare_predicted_single_metric(
        canonical_df,
        metric_id=SINGLE_METRIC_ID,
        country_codes=COUNTRIES,
        forecast_horizon=2,
        horizon_years=2,
        method="linear_trend",
        fallback_method="last_observed",
        comparison_options={"metrics_config": metrics_config},
    )

    outputs = {
        "single_metric_comparison.csv": single_metric_df,
        "multi_metric_comparison.csv": multi_metric_df,
        "weighted_score.csv": weighted_score_df,
        "forecast_table.csv": forecast_table_df,
        "predicted_single_metric_comparison.csv": predicted_comparison.comparison_df,
    }

    exported_tables = export_tables_csv(outputs, output_dir)

    diagnostics_path = export_diagnostics_json(
        {
            "input_rows": len(canonical_df),
            "country_count": int(canonical_df["country_code"].nunique()),
            "metric_count": int(canonical_df["metric_id"].nunique()),
            "prediction_diagnostics": prediction_result.diagnostics,
            "predicted_comparison_metadata": predicted_comparison.metadata,
        },
        output_dir / "diagnostics.json",
    )

    summary_path = export_markdown_summary(
        output_dir / "summary.md",
        title="Country Compare Golden Demo Summary",
        sections={
            "Dataset": [
                f"Input rows: {len(canonical_df)}",
                f"Countries: {canonical_df['country_code'].nunique()}",
                f"Metrics: {canonical_df['metric_id'].nunique()}",
            ],
            "Generated outputs": [str(path) for path in exported_tables.values()],
            "Diagnostics": [str(diagnostics_path)],
        },
    )

    print("Golden demo completed successfully.")
    print(f"Input rows: {len(canonical_df)}")
    print(f"Countries: {canonical_df['country_code'].nunique()}")
    print(f"Metrics: {canonical_df['metric_id'].nunique()}")
    print(f"Output directory: {output_dir}")

    for path in exported_tables.values():
        print(f"- {path}")

    print(f"- {diagnostics_path}")
    print(f"- {summary_path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
