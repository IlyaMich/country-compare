from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from country_compare.config.loader import load_configuration_bundle
from country_compare.config.validator import ConfigurationValidationError

pytestmark = pytest.mark.integration


def _write_yaml(path: Path, payload: dict[str, object]) -> None:
    path.write_text(yaml.safe_dump(payload, sort_keys=True), encoding="utf-8")


def test_config_validation_rejects_unknown_profile_metric(tmp_path) -> None:
    metrics_path = tmp_path / "metrics.yaml"
    scoring_path = tmp_path / "scoring_profiles.yaml"

    _write_yaml(
        metrics_path,
        {
            "metrics": {
                "known_metric": {
                    "display_name": "Known Metric",
                    "category": "test",
                    "higher_is_better": True,
                    "default_weight": 1.0,
                    "unit": "index",
                    "source": "Test Source",
                    "normalization_method": "minmax",
                }
            }
        },
    )

    _write_yaml(
        scoring_path,
        {
            "default_profile": "default",
            "profiles": {
                "default": {
                    "metrics": ["unknown_metric"],
                }
            },
        },
    )

    with pytest.raises(
        ConfigurationValidationError,
        match="references undefined metrics",
    ):
        load_configuration_bundle(metrics_path, scoring_path, validate=True)


def test_config_validation_rejects_weights_for_metrics_not_in_profile(tmp_path) -> None:
    metrics_path = tmp_path / "metrics.yaml"
    scoring_path = tmp_path / "scoring_profiles.yaml"

    _write_yaml(
        metrics_path,
        {
            "metrics": {
                "known_metric": {
                    "display_name": "Known Metric",
                    "category": "test",
                    "higher_is_better": True,
                    "default_weight": 1.0,
                    "unit": "index",
                    "source": "Test Source",
                    "normalization_method": "minmax",
                },
                "other_metric": {
                    "display_name": "Other Metric",
                    "category": "test",
                    "higher_is_better": True,
                    "default_weight": 1.0,
                    "unit": "index",
                    "source": "Test Source",
                    "normalization_method": "minmax",
                },
            }
        },
    )

    _write_yaml(
        scoring_path,
        {
            "default_profile": "default",
            "profiles": {
                "default": {
                    "metrics": ["known_metric"],
                    "weights": {
                        "other_metric": 1.0,
                    },
                }
            },
        },
    )

    with pytest.raises(
        ConfigurationValidationError,
        match="defines weights for metrics not included",
    ):
        load_configuration_bundle(metrics_path, scoring_path, validate=True)


def test_config_validation_rejects_missing_default_profile(tmp_path) -> None:
    metrics_path = tmp_path / "metrics.yaml"
    scoring_path = tmp_path / "scoring_profiles.yaml"

    _write_yaml(
        metrics_path,
        {
            "metrics": {
                "known_metric": {
                    "display_name": "Known Metric",
                    "category": "test",
                    "higher_is_better": True,
                    "default_weight": 1.0,
                    "unit": "index",
                    "source": "Test Source",
                    "normalization_method": "minmax",
                }
            }
        },
    )

    _write_yaml(
        scoring_path,
        {
            "default_profile": "missing_profile",
            "profiles": {
                "default": {
                    "metrics": ["known_metric"],
                }
            },
        },
    )

    with pytest.raises(ValueError, match="default_profile"):
        load_configuration_bundle(metrics_path, scoring_path, validate=True)
