from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import streamlit as st

from country_compare.config.models import YearStrategy
from country_compare.ui import state

PAGE_PARAM = "page"
MODE_PARAM = "mode"
COUNTRIES_PARAM = "countries"
SINGLE_METRIC_PARAM = "metric"
MULTI_METRICS_PARAM = "metrics"
PROFILE_PARAM = "profile"
YEAR_STRATEGY_PARAM = "year_strategy"
TARGET_YEAR_PARAM = "target_year"

VALID_MODES = {"single_metric", "multi_metric", "weighted_score"}


def build_selection_state_from_query_params(params: Mapping[str, Any]) -> dict[str, Any]:
    active_mode = _coerce_mode(_first_value(params.get(MODE_PARAM)))
    year_strategy = _coerce_year_strategy(_first_value(params.get(YEAR_STRATEGY_PARAM)))
    target_year = _coerce_int(_first_value(params.get(TARGET_YEAR_PARAM)))

    return {
        "active_mode": active_mode,
        "selected_countries": _split_csv_codes(_first_value(params.get(COUNTRIES_PARAM))),
        "single_metric_id": _clean_text(_first_value(params.get(SINGLE_METRIC_PARAM))) or None,
        "multi_metric_ids": _split_csv_values(_first_value(params.get(MULTI_METRICS_PARAM))),
        "weighted_profile_name": _clean_text(_first_value(params.get(PROFILE_PARAM))) or None,
        "year_strategy": year_strategy.value,
        "target_year": target_year,
    }


def build_query_params(*, selected_page: str, selection_state: Mapping[str, Any]) -> dict[str, str]:
    params: dict[str, str] = {PAGE_PARAM: str(selected_page)}
    if str(selected_page) != "Compare":
        return params

    active_mode = _coerce_mode(selection_state.get("active_mode"))
    year_strategy = _coerce_year_strategy(selection_state.get("year_strategy"))
    countries = _split_csv_codes(selection_state.get("selected_countries"))
    single_metric_id = _clean_text(selection_state.get("single_metric_id"))
    multi_metric_ids = _split_csv_values(selection_state.get("multi_metric_ids"))
    weighted_profile_name = _clean_text(selection_state.get("weighted_profile_name"))
    target_year = _coerce_int(selection_state.get("target_year"))

    params[MODE_PARAM] = active_mode
    params[YEAR_STRATEGY_PARAM] = year_strategy.value

    if countries:
        params[COUNTRIES_PARAM] = ",".join(countries)
    if year_strategy == YearStrategy.TARGET_YEAR and target_year is not None:
        params[TARGET_YEAR_PARAM] = str(target_year)

    if active_mode == "single_metric" and single_metric_id:
        params[SINGLE_METRIC_PARAM] = single_metric_id
    elif active_mode == "multi_metric" and multi_metric_ids:
        params[MULTI_METRICS_PARAM] = ",".join(multi_metric_ids)
    elif active_mode == "weighted_score" and weighted_profile_name:
        params[PROFILE_PARAM] = weighted_profile_name

    return params


def apply_query_params_once() -> None:
    state.initialize_session_state()
    if state.query_state_initialized():
        return

    raw_params = {key: value for key, value in st.query_params.items()}
    selected_page = _coerce_page(_first_value(raw_params.get(PAGE_PARAM)))
    state.set_selected_page(selected_page)

    if selected_page == "Compare":
        state.set_selection_state(build_selection_state_from_query_params(raw_params))

    state.mark_query_state_initialized(True)


def sync_query_params_from_state(*, selected_page: str, selection_state: Mapping[str, Any]) -> None:
    target = build_query_params(selected_page=selected_page, selection_state=selection_state)
    current = {
        key: _first_value(value)
        for key, value in st.query_params.items()
    }
    if current == target:
        return

    st.query_params.clear()
    for key, value in target.items():
        st.query_params[key] = value


def _coerce_page(value: Any) -> str:
    text = _clean_text(value)
    if text in {"Overview", "Compare", "Config Editor"}:
        return text
    return "Overview"


def _coerce_mode(value: Any) -> str:
    text = _clean_text(value)
    return text if text in VALID_MODES else "single_metric"


def _coerce_year_strategy(value: Any) -> YearStrategy:
    try:
        return YearStrategy(_clean_text(value) or YearStrategy.LATEST_PER_METRIC.value)
    except Exception:
        return YearStrategy.LATEST_PER_METRIC


def _coerce_int(value: Any) -> int | None:
    text = _clean_text(value)
    if not text:
        return None
    try:
        return int(text)
    except (TypeError, ValueError):
        return None


def _split_csv_codes(value: Any) -> list[str]:
    values = _split_csv_values(value)
    normalized: list[str] = []
    seen: set[str] = set()
    for item in values:
        code = item.upper()
        if code and code not in seen:
            normalized.append(code)
            seen.add(code)
    return normalized


def _split_csv_values(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, (list, tuple)):
        chunks = [str(item) for item in value]
    else:
        chunks = str(value).split(",")

    normalized: list[str] = []
    seen: set[str] = set()
    for chunk in chunks:
        text = str(chunk).strip()
        if not text or text in seen:
            continue
        normalized.append(text)
        seen.add(text)
    return normalized


def _first_value(value: Any) -> Any:
    if isinstance(value, (list, tuple)):
        return value[0] if value else None
    return value


def _clean_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()
