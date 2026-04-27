from __future__ import annotations

from collections.abc import Iterator

import pytest
import streamlit as st

from country_compare.ui import state
from country_compare.ui.query_state import (
    apply_query_params_once,
    build_compare_selection_state_from_query_params,
    build_prediction_selection_state_from_query_params,
    build_query_params,
    sync_query_params_from_state,
)


class FakeQueryParams(dict[str, str]):
    def clear(
        self,
    ) -> None:  # pragma: no cover - trivial override for parity with Streamlit API
        super().clear()

    def items(self):  # pragma: no cover - keeps return type predictable in tests
        return super().items()


@pytest.fixture(autouse=True)
def clear_streamlit_state() -> Iterator[None]:
    st.session_state.clear()
    yield
    st.session_state.clear()


@pytest.fixture
def fake_query_params(monkeypatch: pytest.MonkeyPatch) -> FakeQueryParams:
    params = FakeQueryParams()
    monkeypatch.setattr(
        "country_compare.ui.query_state.st.query_params", params, raising=False
    )
    return params


def test_build_compare_selection_state_from_query_params_normalizes_compare_state() -> (
    None
):
    selection_state = build_compare_selection_state_from_query_params(
        {
            "mode": "multi_metric",
            "countries": " isr , deu , ISR ",
            "metrics": "gdp_per_capita, life_expectancy, gdp_per_capita",
            "year_strategy": "target_year",
            "target_year": "2023",
            "profile": "balanced",
            "metric": "gdp_per_capita",
        }
    )

    assert selection_state == {
        "active_mode": "multi_metric",
        "selected_countries": ["ISR", "DEU"],
        "single_metric_id": "gdp_per_capita",
        "multi_metric_ids": ["gdp_per_capita", "life_expectancy"],
        "weighted_profile_name": "balanced",
        "year_strategy": "target_year",
        "target_year": 2023,
    }


def test_build_query_params_only_emits_active_compare_mode_specific_fields() -> None:
    params = build_query_params(
        selected_page="Compare",
        selection_state={
            "active_mode": "weighted_score",
            "selected_countries": ["ISR", "DEU"],
            "single_metric_id": "gdp_per_capita",
            "multi_metric_ids": ["gdp_per_capita", "life_expectancy"],
            "weighted_profile_name": "balanced",
            "year_strategy": "latest_per_metric",
            "target_year": None,
        },
    )

    assert params == {
        "page": "Compare",
        "mode": "weighted_score",
        "countries": "ISR,DEU",
        "year_strategy": "latest_per_metric",
        "profile": "balanced",
    }


def test_build_prediction_selection_state_from_query_params_normalizes_prediction_state() -> (
    None
):
    selection_state = build_prediction_selection_state_from_query_params(
        {
            "prediction_mode": "predicted_multi_metric_comparison",
            "prediction_country": "isr",
            "prediction_countries": "isr, deu, ISR",
            "prediction_metric": "gdp_per_capita",
            "prediction_metrics": "gdp_per_capita, life_expectancy, gdp_per_capita",
            "prediction_profile": "balanced",
            "prediction_method": "moving_average",
            "prediction_horizon_years": "4",
            "prediction_forecast_year": "2027",
            "prediction_forecast_horizon": "2",
            "prediction_holdout_years": "3",
        }
    )

    assert selection_state == {
        "prediction_active_mode": "predicted_multi_metric_comparison",
        "prediction_country_code": "ISR",
        "prediction_country_codes": ["ISR", "DEU"],
        "prediction_metric_id": "gdp_per_capita",
        "prediction_metric_ids": ["gdp_per_capita", "life_expectancy"],
        "prediction_profile_name": "balanced",
        "prediction_method": "moving_average",
        "prediction_horizon_years": 4,
        "prediction_forecast_year": 2027,
        "prediction_forecast_horizon": 2,
        "prediction_holdout_years": 3,
    }


def test_build_query_params_for_prediction_page_emits_prediction_fields() -> None:
    params = build_query_params(
        selected_page="Prediction",
        selection_state={
            "prediction_active_mode": "predicted_profile_comparison",
            "prediction_country_code": "ISR",
            "prediction_country_codes": ["ISR", "DEU"],
            "prediction_metric_id": "gdp_per_capita",
            "prediction_metric_ids": ["gdp_per_capita", "life_expectancy"],
            "prediction_profile_name": "balanced",
            "prediction_method": "moving_average",
            "prediction_horizon_years": 4,
            "prediction_forecast_year": None,
            "prediction_forecast_horizon": 2,
            "prediction_holdout_years": 3,
        },
    )

    assert params == {
        "page": "Prediction",
        "prediction_mode": "predicted_profile_comparison",
        "prediction_country": "ISR",
        "prediction_countries": "ISR,DEU",
        "prediction_metric": "gdp_per_capita",
        "prediction_metrics": "gdp_per_capita,life_expectancy",
        "prediction_profile": "balanced",
        "prediction_method": "moving_average",
        "prediction_horizon_years": "4",
        "prediction_forecast_horizon": "2",
    }


def test_build_query_params_for_non_compare_or_prediction_page_only_emits_page() -> (
    None
):
    params = build_query_params(
        selected_page="Overview",
        selection_state={
            "active_mode": "single_metric",
            "prediction_active_mode": "single_forecast",
        },
    )

    assert params == {"page": "Overview"}


def test_apply_query_params_once_restores_compare_page_selection_state(
    fake_query_params: FakeQueryParams,
) -> None:
    fake_query_params.update(
        {
            "page": "Compare",
            "mode": "single_metric",
            "countries": "ISR,DEU",
            "metric": "gdp_per_capita",
            "year_strategy": "target_year",
            "target_year": "2022",
        }
    )

    apply_query_params_once()

    snapshot = state.snapshot()
    selection_state = state.get_selection_state()

    assert snapshot.selected_page == "Compare"
    assert selection_state["active_mode"] == "single_metric"
    assert selection_state["selected_countries"] == ["ISR", "DEU"]
    assert selection_state["single_metric_id"] == "gdp_per_capita"
    assert selection_state["year_strategy"] == "target_year"
    assert selection_state["target_year"] == 2022


def test_apply_query_params_once_restores_prediction_page_selection_state(
    fake_query_params: FakeQueryParams,
) -> None:
    fake_query_params.update(
        {
            "page": "Prediction",
            "prediction_mode": "backtest",
            "prediction_country": "ISR",
            "prediction_metric": "gdp_per_capita",
            "prediction_method": "moving_average",
            "prediction_horizon_years": "4",
            "prediction_holdout_years": "3",
        }
    )

    apply_query_params_once()

    snapshot = state.snapshot()
    selection_state = state.get_selection_state()

    assert snapshot.selected_page == "Prediction"
    assert selection_state["prediction_active_mode"] == "backtest"
    assert selection_state["prediction_country_code"] == "ISR"
    assert selection_state["prediction_metric_id"] == "gdp_per_capita"
    assert selection_state["prediction_method"] == "moving_average"
    assert selection_state["prediction_horizon_years"] == 4
    assert selection_state["prediction_holdout_years"] == 3


def test_apply_query_params_once_is_idempotent_after_initialization(
    fake_query_params: FakeQueryParams,
) -> None:
    fake_query_params.update(
        {
            "page": "Compare",
            "mode": "single_metric",
            "countries": "ISR,DEU",
            "metric": "gdp_per_capita",
        }
    )
    apply_query_params_once()

    fake_query_params.clear()
    fake_query_params.update(
        {
            "page": "Prediction",
            "prediction_mode": "backtest",
            "prediction_country": "FRA",
        }
    )
    apply_query_params_once()

    snapshot = state.snapshot()
    selection_state = state.get_selection_state()

    assert snapshot.selected_page == "Compare"
    assert selection_state["active_mode"] == "single_metric"
    assert selection_state["selected_countries"] == ["ISR", "DEU"]
    assert selection_state["single_metric_id"] == "gdp_per_capita"


def test_sync_query_params_from_state_writes_compare_page_params(
    fake_query_params: FakeQueryParams,
) -> None:
    sync_query_params_from_state(
        selected_page="Compare",
        selection_state={
            "active_mode": "multi_metric",
            "selected_countries": ["ISR", "DEU"],
            "multi_metric_ids": ["gdp_per_capita", "life_expectancy"],
            "year_strategy": "latest_per_metric",
            "target_year": None,
        },
    )

    assert dict(fake_query_params) == {
        "page": "Compare",
        "mode": "multi_metric",
        "countries": "ISR,DEU",
        "metrics": "gdp_per_capita,life_expectancy",
        "year_strategy": "latest_per_metric",
    }


def test_sync_query_params_from_state_writes_prediction_page_params(
    fake_query_params: FakeQueryParams,
) -> None:
    sync_query_params_from_state(
        selected_page="Prediction",
        selection_state={
            "prediction_active_mode": "single_forecast",
            "prediction_country_code": "ISR",
            "prediction_metric_id": "gdp_per_capita",
            "prediction_method": "linear_trend",
            "prediction_horizon_years": 3,
            "prediction_forecast_year": None,
            "prediction_forecast_horizon": 1,
            "prediction_holdout_years": 2,
        },
    )

    assert dict(fake_query_params) == {
        "page": "Prediction",
        "prediction_mode": "single_forecast",
        "prediction_country": "ISR",
        "prediction_metric": "gdp_per_capita",
        "prediction_method": "linear_trend",
        "prediction_horizon_years": "3",
        "prediction_forecast_horizon": "1",
    }
