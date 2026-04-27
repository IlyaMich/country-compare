from __future__ import annotations

from pathlib import Path

from country_compare.config.loader import load_configuration_bundle


def validate_config(
    metrics_config_path: str | Path, scoring_config_path: str | Path
) -> None:
    load_configuration_bundle(metrics_config_path, scoring_config_path, validate=True)
