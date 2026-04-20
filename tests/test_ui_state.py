from __future__ import annotations

import pandas as pd
import pytest
import streamlit as st

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
)


@pytest.fixture(autouse=True)
def clear_streamlit_session_state() -> None:
    st.session_state.clear()
    yield
    st.session_state.clear()


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