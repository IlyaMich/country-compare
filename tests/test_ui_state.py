from __future__ import annotations

import pandas as pd
import pytest
from typing import Iterator
import streamlit as st
from copy import deepcopy

from country_compare.ui import state

from country_compare.services.results import ComparisonResult, PresentationResult
from country_compare.ui.state import (
    DEFAULT_RESULT_STATE,
    DEFAULT_SELECTION_STATE,
    get_compare_error,
    get_latest_compare_presentation,
    get_selection_state,
    initialize_session_state,
    set_compare_error,
    set_compare_presentation,
    get_latest_prediction_result,
    get_prediction_error,
    set_prediction_error,
    set_prediction_result,
)

METRICS_DATA = {
    "metrics": {
        "gdp_per_capita": {
            "display_name": "GDP per capita",
            "category": "Economy",
            "higher_is_better": True,
            "default_weight": 1.0,
            "normalization_method": "minmax",
        }
    }
}

SCORING_DATA = {
    "default_profile": "balanced",
    "weight_handling": "normalize",
    "default_year_strategy": "latest_per_metric",
    "default_missing_data_policy": "renormalize_weights",
    "profiles": {
        "balanced": {
            "metrics": ["gdp_per_capita"],
            "weights": {},
            "normalization_overrides": {},
        }
    },
}


class _PredictionError:
    code = "missing_country"
    mode = "single_forecast"


class _PredictionResult:
    mode = "single_forecast"
    ok = True


def _clear() -> None:
    st.session_state.clear()


@pytest.fixture(autouse=True)
def clear_streamlit_session_state() -> Iterator[None]:
    _clear()
    yield
    _clear()


def test_default_selection_state_includes_multi_and_weighted_fields() -> None:
    initialize_session_state()
    selection_state = get_selection_state()

    assert DEFAULT_SELECTION_STATE["active_mode"] == "single_metric"
    assert "multi_metric_ids" in selection_state
    assert "weighted_profile_name" in selection_state
    assert selection_state["multi_metric_ids"] == []
    assert selection_state["weighted_profile_name"] is None


def test_default_result_state_includes_mode_specific_maps() -> None:
    initialize_session_state()

    assert "latest_mode" in DEFAULT_RESULT_STATE
    assert "compare_results_by_mode" in DEFAULT_RESULT_STATE
    assert "compare_presentations_by_mode" in DEFAULT_RESULT_STATE
    assert "compare_errors_by_mode" in DEFAULT_RESULT_STATE


def test_set_compare_presentation_stores_mode_specific_results() -> None:
    initialize_session_state()

    compare_result = ComparisonResult(
        mode="multi_metric",
        request=None,
        dataframe=pd.DataFrame([{"country_code": "DEU"}]),
    )
    presentation = PresentationResult(
        mode="multi_metric",
        request=None,
        table=pd.DataFrame([{"country_code": "DEU"}]),
    )

    set_compare_presentation(
        compare_result=compare_result,
        presentation=presentation,
        mode="multi_metric",
    )

    latest = get_latest_compare_presentation(mode="multi_metric")
    assert latest is presentation

    result_state = st.session_state["country_compare.result_state"]
    assert result_state["latest_mode"] == "multi_metric"
    assert result_state["compare_results_by_mode"]["multi_metric"] is compare_result
    assert result_state["compare_presentations_by_mode"]["multi_metric"] is presentation
    assert result_state["compare_errors_by_mode"]["multi_metric"] is None


def test_set_compare_error_stores_mode_specific_error() -> None:
    initialize_session_state()

    class ErrorObj:
        code = "selection_invalid"
        title = "Selection is invalid"
        user_message = "Bad input"
        technical_detail = "trace"
        field_errors = {"metric_ids": "Missing"}

    error = ErrorObj()
    set_compare_error(error, mode="weighted_score")

    stored = get_compare_error(mode="weighted_score")
    assert stored is error

    result_state = st.session_state["country_compare.result_state"]
    assert result_state["latest_mode"] == "weighted_score"
    assert result_state["compare_errors_by_mode"]["weighted_score"] is error
    assert st.session_state["country_compare.last_error_code"] == "selection_invalid"

def _patch_session_state(monkeypatch):
    store = {}
    monkeypatch.setattr(state, "_session_state", lambda: store)
    return store


def test_initialize_config_editor_draft_sets_clean_snapshot(monkeypatch) -> None:
    _patch_session_state(monkeypatch)

    state.initialize_session_state()
    state.initialize_config_editor_draft(
        metrics_data=METRICS_DATA,
        scoring_data=SCORING_DATA,
        force=True,
    )

    editor_state = state.get_config_editor_state()
    assert editor_state["draft_metrics_data"] == METRICS_DATA
    assert editor_state["draft_scoring_data"] == SCORING_DATA
    assert editor_state["selected_metric_id"] == "gdp_per_capita"
    assert editor_state["selected_profile_name"] == "balanced"
    assert editor_state["dirty"] is False


def test_set_config_editor_drafts_marks_dirty_and_reset_restores(monkeypatch) -> None:
    _patch_session_state(monkeypatch)

    state.initialize_session_state()
    state.initialize_config_editor_draft(
        metrics_data=METRICS_DATA,
        scoring_data=SCORING_DATA,
        force=True,
    )

    updated_metrics = deepcopy(METRICS_DATA)
    updated_metrics["metrics"]["gdp_per_capita"]["display_name"] = "GDP per person"
    state.set_config_editor_drafts(metrics_data=updated_metrics)

    assert state.config_editor_is_dirty() is True
    assert state.get_config_editor_state()["validation_report"] is None

    state.reset_config_editor_draft()

    editor_state = state.get_config_editor_state()
    assert editor_state["draft_metrics_data"] == METRICS_DATA
    assert editor_state["dirty"] is False


def test_commit_config_editor_saved_state_clears_dirty(monkeypatch) -> None:
    _patch_session_state(monkeypatch)

    state.initialize_session_state()
    state.initialize_config_editor_draft(
        metrics_data=METRICS_DATA,
        scoring_data=SCORING_DATA,
        force=True,
    )

    updated_metrics = deepcopy(METRICS_DATA)
    updated_metrics["metrics"]["gdp_per_capita"]["display_name"] = "GDP per person"
    state.set_config_editor_drafts(metrics_data=updated_metrics)

    state.commit_config_editor_saved_state(
        metrics_data=updated_metrics,
        scoring_data=SCORING_DATA,
    )

    editor_state = state.get_config_editor_state()
    assert editor_state["loaded_metrics_data"] == updated_metrics
    assert editor_state["draft_metrics_data"] == updated_metrics
    assert editor_state["dirty"] is False


def test_default_prediction_selection_state_fields_are_initialized() -> None:
    initialize_session_state()
    selection_state = get_selection_state()

    assert DEFAULT_SELECTION_STATE["prediction_active_mode"] == "single_forecast"
    assert selection_state["prediction_country_codes"] == []
    assert selection_state["prediction_metric_ids"] == []
    assert selection_state["prediction_method"] == "linear_trend"
    assert selection_state["prediction_horizon_years"] == 3
    assert selection_state["prediction_holdout_years"] == 2


def test_default_prediction_result_state_maps_are_initialized() -> None:
    initialize_session_state()

    assert "latest_prediction_mode" in DEFAULT_RESULT_STATE
    assert "prediction_results_by_mode" in DEFAULT_RESULT_STATE
    assert "prediction_errors_by_mode" in DEFAULT_RESULT_STATE


def test_set_prediction_result_stores_mode_specific_result() -> None:
    initialize_session_state()
    result = _PredictionResult()

    set_prediction_result(result, mode="single_forecast")

    assert get_latest_prediction_result(mode="single_forecast") is result
    result_state = st.session_state["country_compare.result_state"]
    assert result_state["latest_prediction_mode"] == "single_forecast"
    assert result_state["prediction_results_by_mode"]["single_forecast"] is result
    assert result_state["prediction_errors_by_mode"]["single_forecast"] is None


def test_set_prediction_error_stores_mode_specific_error() -> None:
    initialize_session_state()
    error = _PredictionError()

    set_prediction_error(error, mode="single_forecast")

    assert get_prediction_error(mode="single_forecast") is error
    result_state = st.session_state["country_compare.result_state"]
    assert result_state["latest_prediction_mode"] == "single_forecast"
    assert result_state["prediction_errors_by_mode"]["single_forecast"] is error
    assert st.session_state["country_compare.last_error_code"] == "missing_country"
