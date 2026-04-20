from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

import streamlit as st


class StateKey(StrEnum):
    SELECTED_PAGE = "country_compare.selected_page"
    DEBUG_MODE = "country_compare.debug_mode"
    LAST_ERROR_CODE = "country_compare.last_error_code"


@dataclass(frozen=True)
class UIStateSnapshot:
    selected_page: str
    debug_mode: bool
    last_error_code: str | None


DEFAULT_PAGE = "Overview"


def initialize_session_state(*, default_debug: bool = False) -> None:
    st.session_state.setdefault(StateKey.SELECTED_PAGE, DEFAULT_PAGE)
    st.session_state.setdefault(StateKey.DEBUG_MODE, default_debug)
    st.session_state.setdefault(StateKey.LAST_ERROR_CODE, None)


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
