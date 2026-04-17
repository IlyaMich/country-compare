from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from country_compare.config.models import (
    ConfigurationBundle,
    MetricsConfig,
    ScoringConfig,
)
from country_compare.config.validator import validate_configuration_bundle


def _read_yaml(path: str | Path) -> dict[str, Any]:
    yaml_path = Path(path)
    if not yaml_path.exists():
        raise FileNotFoundError(f"YAML file not found: {yaml_path}")

    with yaml_path.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}

    if not isinstance(data, dict):
        raise ValueError(f"Expected top-level mapping in YAML file: {yaml_path}")

    return data


def load_metrics_config(path: str | Path) -> MetricsConfig:
    raw = _read_yaml(path)
    return MetricsConfig.model_validate(raw)


def load_scoring_config(path: str | Path) -> ScoringConfig:
    raw = _read_yaml(path)
    return ScoringConfig.model_validate(raw)


def load_configuration_bundle(
    metrics_path: str | Path,
    scoring_path: str | Path,
    *,
    validate: bool = True,
) -> ConfigurationBundle:
    metrics_config = load_metrics_config(metrics_path)
    scoring_config = load_scoring_config(scoring_path)

    bundle = ConfigurationBundle(metrics=metrics_config, scoring=scoring_config)

    if validate:
        validate_configuration_bundle(bundle)

    return bundle