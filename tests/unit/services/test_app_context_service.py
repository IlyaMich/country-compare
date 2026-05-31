from __future__ import annotations

from pathlib import Path

import pytest

from country_compare.services import AppContext


def _write_required_configs(base_dir: Path) -> tuple[Path, Path]:
    metrics_path = base_dir / "metrics.yaml"
    scoring_path = base_dir / "scoring_profiles.yaml"

    metrics_path.write_text(
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

    scoring_path.write_text(
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

    return metrics_path, scoring_path


def test_app_context_resolves_runtime_paths_to_absolute(tmp_path: Path) -> None:
    metrics_path, scoring_path = _write_required_configs(tmp_path)

    context = AppContext(
        metrics_config_path=metrics_path,
        scoring_config_path=scoring_path,
        audit_dir=tmp_path / "audit",
        export_dir=tmp_path / "exports",
    )

    assert context.metrics_config_path.is_absolute()
    assert context.scoring_config_path.is_absolute()
    assert context.audit_dir.is_absolute()
    assert context.export_dir.is_absolute()
    assert context.settings is not None
    assert context.settings.paths.metrics_config_path == context.metrics_config_path


def test_app_context_missing_metrics_config_fails_clearly(tmp_path: Path) -> None:
    scoring_path = tmp_path / "scoring_profiles.yaml"
    scoring_path.write_text("profiles: {}\n", encoding="utf-8")

    with pytest.raises(FileNotFoundError, match="Metrics config"):
        AppContext(
            metrics_config_path=tmp_path / "missing_metrics.yaml",
            scoring_config_path=scoring_path,
        )


def test_app_context_missing_scoring_config_fails_clearly(tmp_path: Path) -> None:
    metrics_path = tmp_path / "metrics.yaml"
    metrics_path.write_text("metrics: {}\n", encoding="utf-8")

    with pytest.raises(FileNotFoundError, match="Scoring profiles config"):
        AppContext(
            metrics_config_path=metrics_path,
            scoring_config_path=tmp_path / "missing_scoring.yaml",
        )


def test_app_context_allows_missing_store_path(tmp_path: Path) -> None:
    metrics_path, scoring_path = _write_required_configs(tmp_path)

    context = AppContext(
        metrics_config_path=metrics_path,
        scoring_config_path=scoring_path,
        store_path=tmp_path / "missing.parquet",
    )

    assert context.store_path == (tmp_path / "missing.parquet").resolve()
