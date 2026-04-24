from __future__ import annotations

from pathlib import Path

import pandas as pd
import yaml

from country_compare.data.access import save_metric_dataframe
from country_compare.data.examples import build_example_metric_dataframe
from country_compare.data.stores.parquet_store import ParquetMetricStore
from country_compare.services import AppContext, ConfigService, DatasetService

MINIMAL_METRICS = {
    "metrics": {
        "gdp_per_capita": {
            "display_name": "GDP per capita",
            "category": "Economy",
            "higher_is_better": True,
            "default_weight": 1.0,
            "normalization_method": "minmax",
        },
        "life_expectancy": {
            "display_name": "Life expectancy",
            "category": "Health",
            "higher_is_better": True,
            "default_weight": 1.0,
            "normalization_method": "minmax",
        },
    }
}

MINIMAL_SCORING = {
    "default_profile": "balanced",
    "weight_handling": "normalize",
    "default_year_strategy": "latest_per_metric",
    "default_missing_data_policy": "renormalize_weights",
    "profiles": {
        "balanced": {
            "metrics": ["gdp_per_capita", "life_expectancy"],
            "weights": {
                "gdp_per_capita": 0.5,
                "life_expectancy": 0.5,
            },
        }
    },
}


class StubDatasetService:
    def __init__(self, dataframe: pd.DataFrame) -> None:
        self._dataframe = dataframe

    def load_dataframe(self) -> pd.DataFrame:
        return self._dataframe.copy(deep=True)


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

    metrics_path.write_text(
        yaml.safe_dump(metrics_payload, sort_keys=False), encoding="utf-8"
    )
    scoring_path.write_text(
        yaml.safe_dump(scoring_payload, sort_keys=False), encoding="utf-8"
    )
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


def _write_yaml(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        yaml.safe_dump(payload, handle, sort_keys=False, allow_unicode=True)


def test_load_bundle_data_returns_editor_friendly_dicts(tmp_path: Path) -> None:
    metrics_path = tmp_path / "metrics.yaml"
    scoring_path = tmp_path / "scoring_profiles.yaml"
    _write_yaml(metrics_path, MINIMAL_METRICS)
    _write_yaml(scoring_path, MINIMAL_SCORING)

    service = ConfigService(
        context=AppContext(
            metrics_config_path=metrics_path,
            scoring_config_path=scoring_path,
        )
    )

    payload = service.load_bundle_data(validate=False)

    assert (
        payload["metrics"]["metrics"]["gdp_per_capita"]["display_name"]
        == "GDP per capita"
    )
    assert payload["scoring"]["default_profile"] == "balanced"
    assert (
        payload["scoring"]["profiles"]["balanced"]["weights"]["gdp_per_capita"] == 0.5
    )


def test_validate_bundle_data_can_check_against_dataset(tmp_path: Path) -> None:
    metrics_path = tmp_path / "metrics.yaml"
    scoring_path = tmp_path / "scoring_profiles.yaml"
    _write_yaml(metrics_path, MINIMAL_METRICS)
    _write_yaml(scoring_path, MINIMAL_SCORING)

    dataframe = pd.DataFrame(
        {
            "country_code": ["ISR", "DEU"],
            "country_name": ["Israel", "Germany"],
            "metric_id": ["gdp_per_capita", "unknown_metric"],
            "metric_name": ["GDP per capita", "Unknown metric"],
            "value": [1.0, 2.0],
            "year": [2022, 2022],
            "higher_is_better": [True, True],
        }
    )
    service = ConfigService(
        context=AppContext(
            metrics_config_path=metrics_path,
            scoring_config_path=scoring_path,
        ),
        dataset_service=StubDatasetService(dataframe),
    )

    report = service.validate_bundle_data(
        metrics_data=MINIMAL_METRICS,
        scoring_data=MINIMAL_SCORING,
        against_dataset=True,
    )

    assert report.valid is False
    assert report.error is not None
    assert any("not defined in config" in message for message in report.messages)


def test_save_bundle_round_trips_updated_configuration(tmp_path: Path) -> None:
    metrics_path = tmp_path / "metrics.yaml"
    scoring_path = tmp_path / "scoring_profiles.yaml"
    _write_yaml(metrics_path, MINIMAL_METRICS)
    _write_yaml(scoring_path, MINIMAL_SCORING)

    service = ConfigService(
        context=AppContext(
            metrics_config_path=metrics_path,
            scoring_config_path=scoring_path,
        )
    )

    updated_metrics = service.load_bundle_data(validate=False)["metrics"]
    updated_scoring = service.load_bundle_data(validate=False)["scoring"]
    updated_metrics["metrics"]["gdp_per_capita"]["display_name"] = "GDP per person"
    updated_scoring["profiles"]["balanced"]["description"] = "Balanced starter profile"

    bundle = service.build_bundle_from_data(
        metrics_data=updated_metrics,
        scoring_data=updated_scoring,
        validate=True,
    )
    service.save_bundle(bundle)

    reloaded = service.load_bundle_data(validate=False)
    assert (
        reloaded["metrics"]["metrics"]["gdp_per_capita"]["display_name"]
        == "GDP per person"
    )
    assert (
        reloaded["scoring"]["profiles"]["balanced"]["description"]
        == "Balanced starter profile"
    )
