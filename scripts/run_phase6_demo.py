from country_compare.data.examples import build_example_metric_dataframe
from country_compare.metrics.normalization import normalize_metric
from country_compare.metrics.filtering import filter_dataset
from country_compare.metrics.normalization import normalize_dataframe
from country_compare.config.loader import load_metrics_config, load_scoring_config


# --------------------------------------------------
# 1. Normalize a single metric slice
# --------------------------------------------------
df = build_example_metric_dataframe()

gdp_2023 = df[(df["metric_id"] == "gdp_per_capita") & (df["year"] == 2023)]
normalized = normalize_metric(gdp_2023, method="minmax")

print("\n" + "Normalize a single metric slice")
print(normalized[["country_code", "metric_id", "value", "normalized_value"]])


# --------------------------------------------------
# 2. Normalize a filtered dataset
# --------------------------------------------------
df = build_example_metric_dataframe()

filtered = filter_dataset(
    df,
    countries_include=["ISR", "DEU", "SGP"],
    metrics_include=["gdp_per_capita", "rule_of_law"],
    year_strategy="target_year",
    target_year=2022,
)

normalized = normalize_dataframe(filtered, method="minmax")
print("\n" + "Normalize a filtered dataset")
print(
    normalized[
        ["country_code", "metric_id", "year", "value", "normalized_value", "normalization_method"]
    ]
)


# --------------------------------------------------
# 3. Use metric defaults from MetricsConfig
# --------------------------------------------------
metrics_config = load_metrics_config("config/metrics.yaml")
df = build_example_metric_dataframe()

normalized = normalize_dataframe(df, metrics_config=metrics_config)
print("\n" + "Use metric defaults from MetricsConfig")
print(normalized[["metric_id", "value", "normalized_value", "normalization_method"]])


# --------------------------------------------------
# 4. Use scoring-profile normalization overrides
# --------------------------------------------------
metrics_config = load_metrics_config("config/metrics.yaml")
scoring_config = load_scoring_config("config/scoring_profiles.yaml")
df = build_example_metric_dataframe()

normalized = normalize_dataframe(
    df,
    metrics_config=metrics_config,
    scoring_config=scoring_config,
    profile_name="economic_focus",
)
print("\n" + "Use scoring-profile normalization overrides")
print(
    normalized[
        ["country_code", "metric_id", "value", "normalized_value", "normalization_method"]
    ]
)