from __future__ import annotations

from pathlib import Path

import pytest

from country_compare.services import AppContext


@pytest.fixture()
def fake_app_context(tmp_path: Path) -> AppContext:

    config_dir = tmp_path / "config"
    data_dir = tmp_path / "data"
    processed_dir = data_dir / "processed"
    audit_dir = data_dir / "audit"
    export_dir = data_dir / "exports"

    config_dir.mkdir(parents=True, exist_ok=True)

    metrics_config_path = config_dir / "metrics.yaml"
    scoring_config_path = config_dir / "scoring_profiles.yaml"

    metrics_config_path.write_text(
        """
    metrics:
      gdp:
        display_name: GDP
        category: economy
        higher_is_better: true
        default_weight: 1.0
        unit: USD
        normalization_method: minmax
    """.lstrip(),
        encoding="utf-8",
    )

    scoring_config_path.write_text(
        """
    default_profile: default
    weight_handling: normalize
    default_year_strategy: latest_per_metric
    default_missing_data_policy: renormalize_weights
    profiles:
      default:
        metrics:
          - gdp
        weights: {}
        normalization_overrides: {}
    """.lstrip(),
        encoding="utf-8",
    )

    processed_dir.mkdir(parents=True, exist_ok=True)
    audit_dir.mkdir(parents=True, exist_ok=True)
    export_dir.mkdir(parents=True, exist_ok=True)

    return AppContext(
        metrics_config_path=metrics_config_path,
        scoring_config_path=scoring_config_path,
        store_backend="parquet",
        store_path=processed_dir / "metrics.parquet",
        audit_dir=audit_dir,
        export_dir=export_dir,
        debug=False,
    )
