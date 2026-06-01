from __future__ import annotations

import os
from pathlib import Path

import pandas as pd
import pytest

from country_compare.config.loader import load_metrics_config
from country_compare.config.validator import validate_metrics_against_dataframe
from country_compare.paths import METRICS_CONFIG_PATH

pytestmark = pytest.mark.integration

DATA_CORRECTNESS_PATH_ENV = "COUNTRY_COMPARE_DATA_CORRECTNESS_PATH"


def _load_release_dataframe_or_skip() -> pd.DataFrame:
    configured_path = os.environ.get(DATA_CORRECTNESS_PATH_ENV)

    if not configured_path:
        pytest.skip(
            f"Set {DATA_CORRECTNESS_PATH_ENV}=data\\processed\\metrics.parquet "
            "to validate config against a real release dataset."
        )

    path = Path(configured_path)
    if not path.exists():
        pytest.fail(f"{DATA_CORRECTNESS_PATH_ENV} points to missing file: {path}")

    return pd.read_parquet(path)


def test_release_dataset_metric_ids_are_defined_in_metrics_config() -> None:
    dataframe = _load_release_dataframe_or_skip()
    metrics_config = load_metrics_config(METRICS_CONFIG_PATH)

    dataset_metric_ids = set(dataframe["metric_id"].dropna().astype(str).unique())
    configured_metric_ids = set(metrics_config.metrics)

    undefined_metric_ids = sorted(dataset_metric_ids - configured_metric_ids)

    assert undefined_metric_ids == []


def test_release_dataset_metric_metadata_matches_metrics_config() -> None:
    dataframe = _load_release_dataframe_or_skip()
    metrics_config = load_metrics_config(METRICS_CONFIG_PATH)

    validate_metrics_against_dataframe(metrics_config, dataframe)


def test_metrics_config_has_dataset_coverage_for_configured_metrics_when_release_data_is_set() -> (
    None
):
    dataframe = _load_release_dataframe_or_skip()
    metrics_config = load_metrics_config(METRICS_CONFIG_PATH)

    dataset_metric_ids = set(dataframe["metric_id"].dropna().astype(str).unique())
    configured_metric_ids = set(metrics_config.metrics)

    missing_from_dataset = sorted(configured_metric_ids - dataset_metric_ids)

    assert missing_from_dataset == []
