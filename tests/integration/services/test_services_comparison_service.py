from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

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
from country_compare.scoring.weighted_score import ScoringError
from country_compare.services.comparison_service import ComparisonService
from country_compare.services.requests import (
    MultiMetricRequest,
    SingleMetricRequest,
    WeightedScoreRequest,
)


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

    def _invoke_multi_metric_compare(self, *, dataframe, bundle, request):
        result = dataframe.loc[
            (dataframe["country_code"].isin(request.countries))
            & (dataframe["metric_id"].isin(request.metric_ids))
        ].copy()
        result = result.sort_values(["metric_id", "country_code"]).reset_index(drop=True)
        result["normalized_value"] = [0.8, 1.0, 1.0, 0.7]
        result["normalization_method"] = "minmax"
        result["rank"] = [2, 1, 1, 2]
        return result

    def _invoke_weighted_score(self, *, dataframe, bundle, request):
        result = pd.DataFrame(
            [
                {
                    "country_code": "DEU",
                    "country_name": "Germany",
                    "weighted_score": 0.95,
                    "score_rank": 1,
                    "profile_name": request.profile_name,
                    "missing_data_policy": "renormalize_weights",
                    "metric_count_used": 2,
                    "metric_count_expected": 2,
                    "missing_metric_count": 0,
                    "missing_metrics": pd.NA,
                    "weight_sum_used": 1.0,
                    "year_strategy": "latest_per_metric",
                    "score_rank_method": "competition_min",
                },
                {
                    "country_code": "ISR",
                    "country_name": "Israel",
                    "weighted_score": 0.80,
                    "score_rank": 2,
                    "profile_name": request.profile_name,
                    "missing_data_policy": "renormalize_weights",
                    "metric_count_used": 1,
                    "metric_count_expected": 2,
                    "missing_metric_count": 1,
                    "missing_metrics": "life_expectancy",
                    "weight_sum_used": 1.0,
                    "year_strategy": "latest_per_metric",
                    "score_rank_method": "competition_min",
                },
            ]
        )
        return result


class ErroringWeightedService(StubComparisonService):
    def _invoke_weighted_score(self, *, dataframe, bundle, request):
        raise ScoringError("boom")


def _bundle() -> ConfigurationBundle:
    metrics = MetricsConfig(
        metrics={
            "gdp_per_capita": MetricConfig(
                display_name="GDP per capita",
                category="economy",
                higher_is_better=True,
                default_weight=0.6,
                unit="USD",
                normalization_method=NormalizationMethod.MINMAX,
            ),
            "life_expectancy": MetricConfig(
                display_name="Life expectancy",
                category="health",
                higher_is_better=True,
                default_weight=0.4,
                unit="years",
                normalization_method=NormalizationMethod.MINMAX,
            ),
        }
    )
    scoring = ScoringConfig(
        default_profile="default",
        weight_handling=WeightHandlingStrategy.NORMALIZE,
        default_year_strategy=YearStrategy.LATEST_PER_METRIC,
        default_missing_data_policy=MissingDataPolicy.RENORMALIZE_WEIGHTS,
        profiles={
            "default": ScoringProfile(
                metrics=["gdp_per_capita", "life_expectancy"],
                description="Default profile",
            ),
            "target_year_profile": ScoringProfile(
                metrics=["gdp_per_capita", "life_expectancy"],
                year_strategy=YearStrategy.TARGET_YEAR,
                description="Requires target year",
            ),
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
            {
                "country_code": "ISR",
                "country_name": "Israel",
                "metric_id": "life_expectancy",
                "metric_name": "Life expectancy",
                "value": 83.0,
                "year": 2023,
                "unit": "years",
                "source_name": "Example",
                "source_url": "https://example.org",
                "higher_is_better": True,
                "category": "health",
            },
            {
                "country_code": "DEU",
                "country_name": "Germany",
                "metric_id": "life_expectancy",
                "metric_name": "Life expectancy",
                "value": 81.0,
                "year": 2023,
                "unit": "years",
                "source_name": "Example",
                "source_url": "https://example.org",
                "higher_is_better": True,
                "category": "health",
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


def test_run_multi_metric_returns_successful_result() -> None:
    service = StubComparisonService(_dataframe(), _bundle())
    request = MultiMetricRequest(
        countries=["ISR", "DEU"],
        metric_ids=["gdp_per_capita", "life_expectancy"],
        year_strategy="latest_per_metric",
    )

    result = service.run_multi_metric(request)

    assert result.ok is True
    assert result.error is None
    assert set(result.dataframe["metric_id"]) == {"gdp_per_capita", "life_expectancy"}
    assert result.metadata["metric_ids"] == ["gdp_per_capita", "life_expectancy"]
    assert result.metadata["countries_returned"] == ["DEU", "ISR"]
    assert result.metadata["metrics_returned"] == ["gdp_per_capita", "life_expectancy"]
    assert result.diagnostics["ranked"] is True


def test_run_multi_metric_preserves_field_errors_on_invalid_metric_selection() -> None:
    service = StubComparisonService(_dataframe(), _bundle())
    request = MultiMetricRequest(
        countries=["ISR", "DEU"],
        metric_ids=["unknown_metric"],
        year_strategy="latest_per_metric",
    )

    result = service.run_multi_metric(request)

    assert result.ok is False
    assert result.error.code == "selection_invalid"
    assert "metric_ids" in (result.error.field_errors or {})


def test_run_weighted_score_returns_successful_result() -> None:
    service = StubComparisonService(_dataframe(), _bundle())
    request = WeightedScoreRequest(
        countries=["ISR", "DEU"],
        profile_name="default",
    )

    result = service.run_weighted_score(request)

    assert result.ok is True
    assert result.error is None
    assert list(result.dataframe["country_code"]) == ["DEU", "ISR"]
    assert result.metadata["profile_name"] == "default"
    assert result.metadata["missing_data_policy"] == "renormalize_weights"
    assert result.metadata["resolved_weights"] == {
        "gdp_per_capita": 0.6,
        "life_expectancy": 0.4,
    }
    assert any("missing metrics" in warning.lower() for warning in result.warnings)


def test_run_weighted_score_requires_target_year_when_profile_uses_target_year() -> None:
    service = StubComparisonService(_dataframe(), _bundle())
    request = WeightedScoreRequest(
        countries=["ISR", "DEU"],
        profile_name="target_year_profile",
    )

    result = service.run_weighted_score(request)

    assert result.ok is False
    assert result.error.code == "selection_invalid"
    assert result.error.field_errors == {
        "target_year": "This scoring profile uses target-year mode, so a target year is required."
    }


def test_run_weighted_score_maps_scoring_errors() -> None:
    service = ErroringWeightedService(_dataframe(), _bundle())
    request = WeightedScoreRequest(
        countries=["ISR", "DEU"],
        profile_name="default",
    )

    result = service.run_weighted_score(request)

    assert result.ok is False
    assert result.error.code == "scoring_failed"
    assert result.error.title == "Weighted scoring failed"