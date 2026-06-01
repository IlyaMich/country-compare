from __future__ import annotations

import pytest

from country_compare.config.loader import (
    load_configuration_bundle,
    load_metrics_config,
    load_scoring_config,
)
from country_compare.config.models import (
    ConfigurationBundle,
    MetricsConfig,
    ScoringConfig,
)
from country_compare.paths import METRICS_CONFIG_PATH, SCORING_CONFIG_PATH

pytestmark = pytest.mark.integration


def test_metrics_config_file_exists() -> None:
    assert METRICS_CONFIG_PATH.exists(), METRICS_CONFIG_PATH


def test_scoring_config_file_exists() -> None:
    assert SCORING_CONFIG_PATH.exists(), SCORING_CONFIG_PATH


def test_load_metrics_config() -> None:
    config = load_metrics_config(METRICS_CONFIG_PATH)

    assert isinstance(config, MetricsConfig)
    assert config.metrics


def test_load_scoring_config() -> None:
    config = load_scoring_config(SCORING_CONFIG_PATH)

    assert isinstance(config, ScoringConfig)
    assert config.profiles
    assert config.default_profile in config.profiles


def test_load_configuration_bundle_with_validation() -> None:
    bundle = load_configuration_bundle(
        METRICS_CONFIG_PATH,
        SCORING_CONFIG_PATH,
        validate=True,
    )

    assert isinstance(bundle, ConfigurationBundle)
    assert bundle.metrics.metrics
    assert bundle.scoring.profiles
    assert bundle.scoring.default_profile in bundle.scoring.profiles


def test_load_configuration_bundle_without_validation() -> None:
    bundle = load_configuration_bundle(
        METRICS_CONFIG_PATH,
        SCORING_CONFIG_PATH,
        validate=False,
    )

    assert isinstance(bundle, ConfigurationBundle)
