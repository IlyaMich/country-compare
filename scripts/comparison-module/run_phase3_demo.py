from country_compare.config.loader import load_configuration_bundle
from country_compare.config.validator import resolve_profile_weights

bundle = load_configuration_bundle(
    "config/metrics.yaml",
    "config/scoring_profiles.yaml",
)

print(bundle.scoring.default_profile)
print(resolve_profile_weights(bundle.metrics, bundle.scoring, "default_profile"))
