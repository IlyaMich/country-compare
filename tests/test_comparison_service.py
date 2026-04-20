from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace

import pandas as pd

from country_compare.config.models import (
    ConfigurationBundle,
    MetricConfig,
    MetricsConfig,
    MissingDataPolicy,
    NormalizationMethod,
    ScoringConfig,
    ScoringProfile,
    WeightHandlingStrategy,
    YearStrategy,
)
from country_compare.services.comparison_service import ComparisonService
from country_compare.services.requests import SingleMetricRequest


@dataclass
class DummyContext:
    metrics_config_path: Path = Path("config/metrics.yaml")
    scoring_config_path: Path = Path("config/scoring.yaml")
    store_backend: str = "parquet"
    store_path: Path | None = None
    debug: bool = False


class StubComparisonService(ComparisonService):
    def __init__(self, dataframe: pd.DataFrame, bundle: ConfigurationBundle) -> None:
        super().__init__(context=DummyContext())
        self._dataframe = dataframe
        self._bundle = bundle

    def _load_dataframe(self) -> pd.DataFrame:
        return self._dataframe.copy()

    def _load_configuration_bundle(self) -> ConfigurationBundle:
        return self._bundle

    def _invoke_single_metric_compare(self, *, dataframe, bundle, request):
        result = dataframe.loc[
            (dataframe["country_code"].isin(request.countries))
            & (dataframe["metric_id"] == request.metric_id)
        ].copy()
        result["normalized_value"] = [0.5, 1.0]
        result["normalization_method"] = "minmax"
        result["rank"] = [2, 1]
        return result


def _bundle() -> ConfigurationBundle:
    metrics = MetricsConfig(
        metrics={
            "gdp_per_capita": MetricConfig(
                display_name="GDP per capita",
                category="economy",
                higher_is_better=True,
                default_weight=1.0,
                unit="USD",
                normalization_method=NormalizationMethod.MINMAX,
            )
        }
    )
    scoring = ScoringConfig(
        default_profile="default",
        weight_handling=WeightHandlingStrategy.NORMALIZE,
        default_year_strategy=YearStrategy.LATEST_PER_METRIC,
        default_missing_data_policy=MissingDataPolicy.RENORMALIZE_WEIGHTS,
        profiles={
            "default": ScoringProfile(metrics=["gdp_per_capita"]),
        },
    )
    return ConfigurationBundle(metrics=metrics, scoring=scoring)


def _dataframe() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "country_code": "ISR",
                "country_name": "Israel",
                "metric_id": "gdp_per_capita",
                "metric_name": "GDP per capita",
                "value": 56000.0,
                "year": 2023,
                "unit": "USD",
                "source_name": "Example",
                "source_url": "https://example.org",
                "higher_is_better": True,
                "category": "economy",
            },
            {
                "country_code": "DEU",
                "country_name": "Germany",
                "metric_id": "gdp_per_capita",
                "metric_name": "GDP per capita",
                "value": 67000.0,
                "year": 2023,
                "unit": "USD",
                "source_name": "Example",
                "source_url": "https://example.org",
                "higher_is_better": True,
                "category": "economy",
            },
        ]
    )


def test_run_single_metric_returns_successful_result() -> None:
    service = StubComparisonService(_dataframe(), _bundle())
    request = SingleMetricRequest(
        countries=["ISR", "DEU"],
        metric_id="gdp_per_capita",
        year_strategy="latest_per_metric",
    )

    result = service.run_single_metric(request)

    assert result.ok is True
    assert result.error is None
    assert list(result.dataframe["country_code"]) == ["ISR", "DEU"]
    assert result.metadata["metric_id"] == "gdp_per_capita"
    assert result.metadata["year_strategy"] == "latest_per_metric"


def test_run_single_metric_preserves_field_errors_on_invalid_selection() -> None:
    service = StubComparisonService(_dataframe(), _bundle())
    request = SingleMetricRequest(
        countries=["ISR"],
        metric_id="gdp_per_capita",
        year_strategy="latest_per_metric",
    )

    result = service.run_single_metric(request)

    assert result.ok is False
    assert result.error.code == "selection_invalid"
    assert "countries" in (result.error.field_errors or {})
