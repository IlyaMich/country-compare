from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

import streamlit as st


class StateKey(StrEnum):
    SELECTED_PAGE = "country_compare.selected_page"
    DEBUG_MODE = "country_compare.debug_mode"
    LAST_ERROR_CODE = "country_compare.last_error_code"
    CATALOG_STATE = "country_compare.catalog_state"
    SELECTION_STATE = "country_compare.selection_state"
    RESULT_STATE = "country_compare.result_state"


@dataclass(frozen=True)
class UIStateSnapshot:
    selected_page: str
    debug_mode: bool
    last_error_code: str | None


DEFAULT_PAGE = "Overview"

DEFAULT_SELECTION_STATE = {
    "active_mode": "single_metric",
    "selected_countries": [],
    "single_metric_id": None,
    "multi_metric_ids": [],
    "weighted_profile_name": None,
    "year_strategy": "latest_per_metric",
    "target_year": None,
}

DEFAULT_RESULT_STATE = {
    "compare_result": None,
    "compare_presentation": None,
    "compare_error": None,
    "latest_mode": "single_metric",
    "compare_results_by_mode": {},
    "compare_presentations_by_mode": {},
    "compare_errors_by_mode": {},
}


def initialize_session_state(*, default_debug: bool = False) -> None:
    st.session_state.setdefault(StateKey.SELECTED_PAGE, DEFAULT_PAGE)
    st.session_state.setdefault(StateKey.DEBUG_MODE, default_debug)
    st.session_state.setdefault(StateKey.LAST_ERROR_CODE, None)

    st.session_state.setdefault(StateKey.CATALOG_STATE, {})
    st.session_state.setdefault(StateKey.SELECTION_STATE, dict(DEFAULT_SELECTION_STATE))
    st.session_state.setdefault(StateKey.RESULT_STATE, dict(DEFAULT_RESULT_STATE))


def snapshot() -> UIStateSnapshot:
    initialize_session_state()
    return UIStateSnapshot(
        selected_page=str(st.session_state[StateKey.SELECTED_PAGE]),
        debug_mode=bool(st.session_state[StateKey.DEBUG_MODE]),
        last_error_code=st.session_state[StateKey.LAST_ERROR_CODE],
    )


def set_selected_page(page_name: str) -> None:
    st.session_state[StateKey.SELECTED_PAGE] = page_name


def set_debug_mode(value: bool) -> None:
    st.session_state[StateKey.DEBUG_MODE] = bool(value)


def set_last_error_code(value: str | None) -> None:
    st.session_state[StateKey.LAST_ERROR_CODE] = value


def get_catalog_state() -> dict:
    initialize_session_state()
    return st.session_state[StateKey.CATALOG_STATE]


def set_catalog_state(value: dict) -> None:
    initialize_session_state()
    st.session_state[StateKey.CATALOG_STATE] = value


def get_selection_state() -> dict:
    initialize_session_state()
    return st.session_state[StateKey.SELECTION_STATE]


def set_selection_state(update: dict) -> None:
    initialize_session_state()
    current = dict(st.session_state[StateKey.SELECTION_STATE])
    current.update(update)
    st.session_state[StateKey.SELECTION_STATE] = current


def get_latest_compare_presentation(mode: str | None = None):
    initialize_session_state()
    result_state = st.session_state[StateKey.RESULT_STATE]
    if mode is not None:
        return result_state.get("compare_presentations_by_mode", {}).get(mode)
    return result_state.get("compare_presentation")


def set_compare_presentation(*, compare_result, presentation, mode: str | None = None) -> None:
    initialize_session_state()
    resolved_mode = mode or getattr(compare_result, "mode", None) or getattr(presentation, "mode", None) or "single_metric"
    current = dict(st.session_state[StateKey.RESULT_STATE])
    results_by_mode = dict(current.get("compare_results_by_mode", {}))
    presentations_by_mode = dict(current.get("compare_presentations_by_mode", {}))
    errors_by_mode = dict(current.get("compare_errors_by_mode", {}))

    results_by_mode[resolved_mode] = compare_result
    presentations_by_mode[resolved_mode] = presentation
    errors_by_mode[resolved_mode] = None

    current.update(
        {
            "compare_result": compare_result,
            "compare_presentation": presentation,
            "compare_error": None,
            "latest_mode": resolved_mode,
            "compare_results_by_mode": results_by_mode,
            "compare_presentations_by_mode": presentations_by_mode,
            "compare_errors_by_mode": errors_by_mode,
        }
    )
    st.session_state[StateKey.RESULT_STATE] = current
    set_last_error_code(None)


def set_compare_error(error, mode: str | None = None) -> None:
    initialize_session_state()
    resolved_mode = mode or st.session_state[StateKey.SELECTION_STATE].get("active_mode", "single_metric")
    current = dict(st.session_state[StateKey.RESULT_STATE])
    errors_by_mode = dict(current.get("compare_errors_by_mode", {}))
    errors_by_mode[resolved_mode] = error
    current.update(
        {
            "compare_error": error,
            "latest_mode": resolved_mode,
            "compare_errors_by_mode": errors_by_mode,
        }
    )
    st.session_state[StateKey.RESULT_STATE] = current
    set_last_error_code(getattr(error, "code", None))


def get_compare_error(mode: str | None = None):
    initialize_session_state()
    result_state = st.session_state[StateKey.RESULT_STATE]
    if mode is not None:
        return result_state.get("compare_errors_by_mode", {}).get(mode)
    return result_state.get("compare_error")


def get_debug_mode() -> bool:
    initialize_session_state()
    return bool(st.session_state[StateKey.DEBUG_MODE])