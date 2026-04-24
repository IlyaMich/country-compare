from __future__ import annotations

import pytest

from country_compare.services.requests import (
    MultiMetricRequest,
    SingleMetricRequest,
    WeightedScoreRequest,
)


def test_single_metric_request_normalizes_countries() -> None:
    request = SingleMetricRequest(
        countries=[" isr ", "DEU", "isr"],
        metric_id="gdp_per_capita",
        year_strategy="latest_per_metric",
    )

    assert request.countries == ["ISR", "DEU"]
    assert request.metric_id == "gdp_per_capita"
    assert request.mode == "single_metric"


def test_multi_metric_request_normalizes_metric_ids_and_countries() -> None:
    request = MultiMetricRequest(
        countries=[" isr ", "deu", "ISR"],
        metric_ids=["gdp_per_capita", " life_expectancy ", "gdp_per_capita"],
        year_strategy="latest_per_metric",
    )

    assert request.countries == ["ISR", "DEU"]
    assert request.metric_ids == ["gdp_per_capita", "life_expectancy"]
    assert request.mode == "multi_metric"


def test_multi_metric_request_rejects_empty_metric_ids() -> None:
    with pytest.raises(ValueError, match="metric_ids must contain at least one metric"):
        MultiMetricRequest(
            countries=["ISR", "DEU"],
            metric_ids=[],
            year_strategy="latest_per_metric",
        )


def test_target_year_strategy_requires_target_year() -> None:
    with pytest.raises(ValueError, match="target_year is required"):
        SingleMetricRequest(
            countries=["ISR", "DEU"],
            metric_id="gdp_per_capita",
            year_strategy="target_year",
        )


def test_weighted_score_request_requires_profile_name() -> None:
    with pytest.raises(ValueError, match="profile_name must be provided"):
        WeightedScoreRequest(
            countries=["ISR", "DEU"],
            profile_name="",
        )


def test_weighted_score_request_normalizes_countries() -> None:
    request = WeightedScoreRequest(
        countries=[" isr ", "deu", "ISR"],
        profile_name="default",
    )

    assert request.countries == ["ISR", "DEU"]
    assert request.profile_name == "default"
    assert request.mode == "weighted_score"