from __future__ import annotations

import pytest

from country_compare.config.loader import load_configuration_bundle, load_scoring_config
from country_compare.config.validator import (
    resolve_profile_options,
    resolve_profile_weights,
    validate_configuration_bundle,
)
from country_compare.paths import METRICS_CONFIG_PATH, SCORING_CONFIG_PATH

pytestmark = pytest.mark.integration


def test_scoring_profiles_reference_known_metrics() -> None:
    bundle = load_configuration_bundle(
        METRICS_CONFIG_PATH,
        SCORING_CONFIG_PATH,
        validate=False,
    )

    known_metric_ids = set(bundle.metrics.metrics)
    failures: list[dict[str, object]] = []

    for profile_name, profile in bundle.scoring.profiles.items():
        unknown_metrics = sorted(set(profile.metrics) - known_metric_ids)

        if unknown_metrics:
            failures.append(
                {
                    "profile_name": profile_name,
                    "unknown_metrics": unknown_metrics,
                }
            )

    assert failures == []


def test_scoring_profile_weights_reference_profile_metrics_only() -> None:
    scoring = load_scoring_config(SCORING_CONFIG_PATH)

    failures: list[dict[str, object]] = []

    for profile_name, profile in scoring.profiles.items():
        profile_metrics = set(profile.metrics)
        unknown_weight_metrics = sorted(set(profile.weights) - profile_metrics)

        if unknown_weight_metrics:
            failures.append(
                {
                    "profile_name": profile_name,
                    "unknown_weight_metrics": unknown_weight_metrics,
                }
            )

    assert failures == []


def test_scoring_profile_normalization_overrides_reference_profile_metrics_only() -> (
    None
):
    scoring = load_scoring_config(SCORING_CONFIG_PATH)

    failures: list[dict[str, object]] = []

    for profile_name, profile in scoring.profiles.items():
        profile_metrics = set(profile.metrics)
        unknown_override_metrics = sorted(
            set(profile.normalization_overrides) - profile_metrics
        )

        if unknown_override_metrics:
            failures.append(
                {
                    "profile_name": profile_name,
                    "unknown_override_metrics": unknown_override_metrics,
                }
            )

    assert failures == []


def test_scoring_profiles_have_unique_metric_lists() -> None:
    scoring = load_scoring_config(SCORING_CONFIG_PATH)

    failures: list[dict[str, object]] = []

    for profile_name, profile in scoring.profiles.items():
        duplicate_metrics = sorted(
            metric_id
            for metric_id in set(profile.metrics)
            if profile.metrics.count(metric_id) > 1
        )

        if duplicate_metrics:
            failures.append(
                {
                    "profile_name": profile_name,
                    "duplicate_metrics": duplicate_metrics,
                }
            )

    assert failures == []


def test_configuration_bundle_validator_accepts_current_config() -> None:
    bundle = load_configuration_bundle(
        METRICS_CONFIG_PATH,
        SCORING_CONFIG_PATH,
        validate=False,
    )

    validate_configuration_bundle(bundle)


def test_resolved_profile_weights_are_positive_and_sum_to_one() -> None:
    bundle = load_configuration_bundle(
        METRICS_CONFIG_PATH,
        SCORING_CONFIG_PATH,
        validate=True,
    )

    failures: list[dict[str, object]] = []

    for profile_name in bundle.scoring.profiles:
        weights = resolve_profile_weights(
            bundle.metrics,
            bundle.scoring,
            profile_name,
        )

        total_weight = sum(weights.values())

        if any(weight <= 0 for weight in weights.values()):
            failures.append(
                {
                    "profile_name": profile_name,
                    "reason": "non_positive_weight",
                    "weights": weights,
                }
            )

        if abs(total_weight - 1.0) > 1e-9:
            failures.append(
                {
                    "profile_name": profile_name,
                    "reason": "weights_do_not_sum_to_one",
                    "total_weight": total_weight,
                    "weights": weights,
                }
            )

    assert failures == []


def test_profile_options_resolve_for_every_profile() -> None:
    bundle = load_configuration_bundle(
        METRICS_CONFIG_PATH,
        SCORING_CONFIG_PATH,
        validate=True,
    )

    failures: list[dict[str, object]] = []

    for profile_name in bundle.scoring.profiles:
        options = resolve_profile_options(bundle.scoring, profile_name)

        if "year_strategy" not in options:
            failures.append(
                {
                    "profile_name": profile_name,
                    "missing": "year_strategy",
                }
            )

        if "missing_data_policy" not in options:
            failures.append(
                {
                    "profile_name": profile_name,
                    "missing": "missing_data_policy",
                }
            )

    assert failures == []


def test_default_profile_is_usable() -> None:
    bundle = load_configuration_bundle(
        METRICS_CONFIG_PATH,
        SCORING_CONFIG_PATH,
        validate=True,
    )

    default_profile_name = bundle.scoring.default_profile

    assert default_profile_name in bundle.scoring.profiles

    weights = resolve_profile_weights(
        bundle.metrics,
        bundle.scoring,
        default_profile_name,
    )

    assert weights
    assert abs(sum(weights.values()) - 1.0) <= 1e-9
