from __future__ import annotations

from pathlib import Path

import yaml

from country_compare.data.access import save_metric_dataframe
from country_compare.data.examples import build_example_metric_dataframe
from country_compare.data.stores.parquet_store import ParquetMetricStore
from country_compare.services import AppContext, ConfigService, DatasetService


def _write_valid_config_files(base_dir: Path) -> tuple[Path, Path]:
    metrics_path = base_dir / "metrics.yaml"
    scoring_path = base_dir / "scoring.yaml"

    metrics_payload = {
        "metrics": {
            "gdp_per_capita": {
                "display_name": "GDP per capita",
                "category": "economy",
                "higher_is_better": True,
                "default_weight": 1.0,
                "description": "Example metric",
                "unit": "USD",
                "source": "Example Source",
                "normalization_method": "minmax",
            },
            "rule_of_law": {
                "display_name": "Rule of Law",
                "category": "governance",
                "higher_is_better": True,
                "default_weight": 1.0,
                "description": "Example metric",
                "unit": "index",
                "source": "Example Source",
                "normalization_method": "minmax",
            },
            "democracy_index": {
                "display_name": "Democracy Index",
                "category": "governance",
                "higher_is_better": True,
                "default_weight": 1.0,
                "description": "Example metric",
                "unit": "score_0_10",
                "source": "Example Source",
                "normalization_method": "minmax",
            },
        }
    }

    scoring_payload = {
        "default_profile": "balanced",
        "weight_handling": "normalize",
        "default_year_strategy": "latest_per_metric",
        "default_missing_data_policy": "renormalize_weights",
        "profiles": {
            "balanced": {
                "metrics": ["gdp_per_capita", "rule_of_law", "democracy_index"],
                "weights": {
                    "gdp_per_capita": 1.0,
                    "rule_of_law": 1.0,
                    "democracy_index": 1.0,
                },
                "description": "Balanced example profile",
            }
        },
    }

    metrics_path.write_text(yaml.safe_dump(metrics_payload, sort_keys=False), encoding="utf-8")
    scoring_path.write_text(yaml.safe_dump(scoring_payload, sort_keys=False), encoding="utf-8")
    return metrics_path, scoring_path


def test_config_service_returns_valid_status(tmp_path: Path) -> None:
    metrics_path, scoring_path = _write_valid_config_files(tmp_path)
    context = AppContext(
        metrics_config_path=metrics_path,
        scoring_config_path=scoring_path,
        store_backend="parquet",
        store_path=tmp_path / "metrics.parquet",
    )

    service = ConfigService(context)
    status = service.get_status()

    assert status.bundle_loaded is True
    assert status.validation.valid is True
    assert status.metrics_count == 3
    assert status.profile_count == 1
    assert status.default_profile == "balanced"


def test_config_service_can_validate_against_dataset(tmp_path: Path) -> None:
    metrics_path, scoring_path = _write_valid_config_files(tmp_path)
    store_path = tmp_path / "metrics.parquet"
    store = ParquetMetricStore(store_path)
    save_metric_dataframe(build_example_metric_dataframe(), store=store)

    context = AppContext(
        metrics_config_path=metrics_path,
        scoring_config_path=scoring_path,
        store_backend="parquet",
        store_path=store_path,
    )
    dataset_service = DatasetService(context)
    service = ConfigService(context, dataset_service=dataset_service)

    report = service.validate_bundle(against_dataset=True)

    # The dataset now contains metrics not defined in the config, so validation should fail
    assert report.valid is False
    assert "dataset contains metric_ids not defined in config" in report.messages[0]
