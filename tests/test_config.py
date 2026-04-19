from pathlib import Path

import pandas as pd
import pytest
import yaml

from country_compare.config.loader import (
    load_configuration_bundle,
    load_metrics_config,
    load_scoring_config,
)
from country_compare.config.models import NormalizationMethod
from country_compare.config.validator import (
    ConfigurationValidationError,
    resolve_profile_weights,
    validate_metrics_against_dataframe,
)


def write_yaml(path: Path, payload: dict) -> None:
    path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")


def test_resolve_profile_options_uses_profile_override_and_global_defaults(
    tmp_path: Path,
    valid_metrics_payload: dict,
    valid_scoring_payload: dict,
) -> None:
    metrics_path = tmp_path / "metrics.yaml"
    scoring_path = tmp_path / "scoring.yaml"

    write_yaml(metrics_path, valid_metrics_payload)
    write_yaml(scoring_path, valid_scoring_payload)

    bundle = load_configuration_bundle(metrics_path, scoring_path)

    from country_compare.config.validator import resolve_profile_options

    resolved = resolve_profile_options(bundle.scoring, "economic_focus")
    assert resolved["year_strategy"] == "common_year"
    assert resolved["missing_data_policy"] == "renormalize_weights"

    resolved_default = resolve_profile_options(bundle.scoring, "default_profile")
    assert resolved_default["year_strategy"] == "latest_per_metric"
    assert resolved_default["missing_data_policy"] == "renormalize_weights"

@pytest.fixture
def valid_metrics_payload() -> dict:
    return {
        "metrics": {
            "gdp_per_capita": {
                "display_name": "GDP per capita",
                "category": "economy",
                "higher_is_better": True,
                "default_weight": 1.0,
                "unit": "USD",
                "normalization_method": "log-minmax",
            },
            "rule_of_law": {
                "display_name": "Rule of Law",
                "category": "governance",
                "higher_is_better": True,
                "default_weight": 1.0,
                "unit": "index",
                "normalization_method": "minmax",
            },
            "inflation": {
                "display_name": "Inflation",
                "category": "economy",
                "higher_is_better": False,
                "default_weight": 0.5,
                "unit": "percent",
                "normalization_method": "rank",
            },
        }
    }


@pytest.fixture
def valid_scoring_payload() -> dict:
    return {
        "default_profile": "default_profile",
        "weight_handling": "normalize",
        "default_year_strategy": "latest_per_metric",
        "default_missing_data_policy": "renormalize_weights",
        "profiles": {
            "default_profile": {
                "metrics": ["gdp_per_capita", "rule_of_law"],
                "weights": {},
                "normalization_overrides": {},
            },
            "economic_focus": {
                "metrics": ["gdp_per_capita", "inflation"],
                "weights": {
                    "gdp_per_capita": 2.0,
                },
                "normalization_overrides": {
                    "inflation": "rank",
                },
                "year_strategy": "common_year",
                "missing_data_policy": "renormalize_weights",
            },
        },
    }


def test_load_metrics_config(tmp_path: Path, valid_metrics_payload: dict) -> None:
    path = tmp_path / "metrics.yaml"
    write_yaml(path, valid_metrics_payload)

    config = load_metrics_config(path)

    assert "gdp_per_capita" in config.metrics
    assert config.metrics["gdp_per_capita"].normalization_method == NormalizationMethod.LOG_MINMAX


def test_load_scoring_config(tmp_path: Path, valid_scoring_payload: dict) -> None:
    path = tmp_path / "scoring.yaml"
    write_yaml(path, valid_scoring_payload)

    config = load_scoring_config(path)

    assert config.default_profile == "default_profile"
    assert "economic_focus" in config.profiles


def test_bundle_validation_rejects_unknown_metric_reference(
    tmp_path: Path,
    valid_metrics_payload: dict,
    valid_scoring_payload: dict,
) -> None:
    metrics_path = tmp_path / "metrics.yaml"
    scoring_path = tmp_path / "scoring.yaml"

    valid_scoring_payload["profiles"]["default_profile"]["metrics"].append("unknown_metric")

    write_yaml(metrics_path, valid_metrics_payload)
    write_yaml(scoring_path, valid_scoring_payload)

    with pytest.raises(ConfigurationValidationError, match="undefined metrics"):
        load_configuration_bundle(metrics_path, scoring_path)


def test_resolve_profile_weights_uses_defaults_and_normalizes(
    tmp_path: Path,
    valid_metrics_payload: dict,
    valid_scoring_payload: dict,
) -> None:
    metrics_path = tmp_path / "metrics.yaml"
    scoring_path = tmp_path / "scoring.yaml"

    write_yaml(metrics_path, valid_metrics_payload)
    write_yaml(scoring_path, valid_scoring_payload)

    bundle = load_configuration_bundle(metrics_path, scoring_path)

    resolved = resolve_profile_weights(bundle.metrics, bundle.scoring, "economic_focus")

    assert set(resolved.keys()) == {"gdp_per_capita", "inflation"}
    assert abs(sum(resolved.values()) - 1.0) < 1e-9
    assert resolved["gdp_per_capita"] > resolved["inflation"]


def test_invalid_normalization_method_fails(tmp_path: Path, valid_metrics_payload: dict) -> None:
    path = tmp_path / "metrics.yaml"
    valid_metrics_payload["metrics"]["gdp_per_capita"]["normalization_method"] = "zscore"
    write_yaml(path, valid_metrics_payload)

    with pytest.raises(Exception):
        load_metrics_config(path)


def test_dataframe_consistency_validation_passes(valid_metrics_payload: dict) -> None:
    metrics = load_metrics_config_from_payload(valid_metrics_payload)

    df = pd.DataFrame(
        [
            {
                "metric_id": "gdp_per_capita",
                "category": "economy",
                "unit": "USD",
                "higher_is_better": True,
            },
            {
                "metric_id": "rule_of_law",
                "category": "governance",
                "unit": "index",
                "higher_is_better": True,
            },
        ]
    )

    validate_metrics_against_dataframe(metrics, df)


def test_dataframe_consistency_validation_rejects_conflict(valid_metrics_payload: dict) -> None:
    metrics = load_metrics_config_from_payload(valid_metrics_payload)

    df = pd.DataFrame(
        [
            {
                "metric_id": "inflation",
                "category": "economy",
                "unit": "percent",
                "higher_is_better": True,
            }
        ]
    )

    with pytest.raises(ConfigurationValidationError, match="conflicting 'higher_is_better'"):
        validate_metrics_against_dataframe(metrics, df)


def load_metrics_config_from_payload(payload: dict):
    from country_compare.config.models import MetricsConfig

    return MetricsConfig.model_validate(payload)