from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

import pandas as pd
import pytest

from country_compare.data.examples import build_example_metric_dataframe

DATA_CORRECTNESS_PATH_ENV = "COUNTRY_COMPARE_DATA_CORRECTNESS_PATH"


@dataclass(frozen=True)
class DataCorrectnessContext:
    dataframe: pd.DataFrame
    source: str
    is_example_dataset: bool


@pytest.fixture(scope="session")
def data_correctness_context() -> DataCorrectnessContext:
    """Load the dataset used by data-correctness integration tests.

    By default, these tests use the deterministic example dataset so they are
    stable in CI and on fresh checkouts.

    To run the same checks against a release parquet file:

        $env:COUNTRY_COMPARE_DATA_CORRECTNESS_PATH = "data/processed/metrics.parquet"
        python -m pytest tests/integration/data
    """
    configured_path = os.environ.get(DATA_CORRECTNESS_PATH_ENV)

    if configured_path:
        path = Path(configured_path)
        return DataCorrectnessContext(
            dataframe=pd.read_parquet(path),
            source=str(path),
            is_example_dataset=False,
        )

    return DataCorrectnessContext(
        dataframe=build_example_metric_dataframe(),
        source="country_compare.data.examples.build_example_metric_dataframe",
        is_example_dataset=True,
    )
