from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from enum import StrEnum
from typing import Any, cast

import streamlit as st

from country_compare.ui.navigation import DEFAULT_PAGE


class StateKey(StrEnum):
    SELECTED_PAGE = "country_compare.selected_page"
    DEBUG_MODE = "country_compare.debug_mode"
    LAST_ERROR_CODE = "country_compare.last_error_code"
    CATALOG_STATE = "country_compare.catalog_state"
    SELECTION_STATE = "country_compare.selection_state"
    RESULT_STATE = "country_compare.result_state"
    CONFIG_EDITOR_STATE = "country_compare.config_editor_state"


@dataclass(frozen=True)
class UIStateSnapshot:
    selected_page: str
    debug_mode: bool
    last_error_code: str | None


DEFAULT_SELECTION_STATE: dict[str, Any] = {
    "active_mode": "single_metric",
    "selected_countries": [],
    "single_metric_id": None,
    "multi_metric_ids": [],
    "weighted_profile_name": None,
    "year_strategy": "latest_per_metric",
    "target_year": None,
    "prediction_active_mode": "single_forecast",
    "prediction_country_code": None,
    "prediction_country_codes": [],
    "prediction_metric_id": None,
    "prediction_metric_ids": [],
    "prediction_profile_name": None,
    "prediction_method": "linear_trend",
    "prediction_horizon_years": 3,
    "prediction_forecast_year": None,
    "prediction_forecast_horizon": 1,
    "prediction_holdout_years": 2,
}

DEFAULT_RESULT_STATE: dict[str, Any] = {
    "latest_mode": "single_metric",
    "compare_result": None,
    "compare_presentation": None,
    "compare_error": None,
    "compare_results_by_mode": {},
    "compare_presentations_by_mode": {},
    "compare_errors_by_mode": {},
    "latest_prediction_mode": "single_forecast",
    "prediction_result": None,
    "prediction_error": None,
    "prediction_results_by_mode": {},
    "prediction_errors_by_mode": {},
}

DEFAULT_CONFIG_EDITOR_STATE: dict[str, Any] = {
    "loaded_metrics_data": None,
    "loaded_scoring_data": None,
    "draft_metrics_data": None,
    "draft_scoring_data": None,
    "selected_metric_id": None,
    "selected_profile_name": None,
    "dirty": False,
    "validation_report": None,
    "validation_against_dataset": False,
    "save_status": None,
    "save_message": None,
    "save_error": None,
}


def _session_state() -> dict[str, Any]:
    return cast(dict[str, Any], st.session_state)


def _get_result_state() -> dict[str, Any]:
    initialize_session_state()
    return _session_state()[StateKey.RESULT_STATE]


def _resolve_compare_mode(
    *,
    mode: str | None = None,
    compare_result=None,
    presentation=None,
    error=None,
) -> str:
    if mode:
        return str(mode)

    for candidate in (presentation, compare_result, error):
        candidate_mode = getattr(candidate, "mode", None)
        if candidate_mode:
            return str(candidate_mode)

    selection_mode = get_selection_state().get("active_mode")
    if selection_mode:
        return str(selection_mode)

    latest_mode = _get_result_state().get("latest_mode")
    if latest_mode:
        return str(latest_mode)

    return "single_metric"


def _resolve_prediction_mode(
    *, mode: str | None = None, result=None, error=None
) -> str:
    if mode:
        return str(mode)

    for candidate in (result, error):
        candidate_mode = getattr(candidate, "mode", None)
        if candidate_mode:
            return str(candidate_mode)

    selection_mode = get_selection_state().get("prediction_active_mode")
    if selection_mode:
        return str(selection_mode)

    latest_mode = _get_result_state().get("latest_prediction_mode")
    if latest_mode:
        return str(latest_mode)

    return "single_forecast"


def initialize_session_state(*, default_debug: bool = False) -> None:
    session = _session_state()
    session.setdefault(StateKey.SELECTED_PAGE, DEFAULT_PAGE)
    session.setdefault(StateKey.DEBUG_MODE, default_debug)
    session.setdefault(StateKey.LAST_ERROR_CODE, None)
    session.setdefault(StateKey.CATALOG_STATE, {})

    session.setdefault(StateKey.SELECTION_STATE, {})
    for key, value in DEFAULT_SELECTION_STATE.items():
        session[StateKey.SELECTION_STATE].setdefault(key, deepcopy(value))

    session.setdefault(StateKey.RESULT_STATE, {})
    for key, value in DEFAULT_RESULT_STATE.items():
        session[StateKey.RESULT_STATE].setdefault(key, deepcopy(value))

    session.setdefault(StateKey.CONFIG_EDITOR_STATE, {})
    for key, value in DEFAULT_CONFIG_EDITOR_STATE.items():
        session[StateKey.CONFIG_EDITOR_STATE].setdefault(key, deepcopy(value))


def snapshot() -> UIStateSnapshot:
    initialize_session_state()
    session = _session_state()
    return UIStateSnapshot(
        selected_page=str(session[StateKey.SELECTED_PAGE]),
        debug_mode=bool(session[StateKey.DEBUG_MODE]),
        last_error_code=session[StateKey.LAST_ERROR_CODE],
    )


def set_selected_page(page_name: str) -> None:
    _session_state()[StateKey.SELECTED_PAGE] = page_name


def set_debug_mode(value: bool) -> None:
    _session_state()[StateKey.DEBUG_MODE] = bool(value)


def set_last_error_code(value: str | None) -> None:
    _session_state()[StateKey.LAST_ERROR_CODE] = value


def get_catalog_state() -> dict[str, Any]:
    initialize_session_state()
    return _session_state()[StateKey.CATALOG_STATE]


def set_catalog_state(value: dict[str, Any]) -> None:
    initialize_session_state()
    _session_state()[StateKey.CATALOG_STATE] = value


def get_selection_state() -> dict[str, Any]:
    initialize_session_state()
    return _session_state()[StateKey.SELECTION_STATE]


def set_selection_state(update: dict[str, Any]) -> None:
    initialize_session_state()
    current = dict(_session_state()[StateKey.SELECTION_STATE])
    current.update(update)
    _session_state()[StateKey.SELECTION_STATE] = current


def get_latest_compare_presentation(mode: str | None = None):
    result_state = _get_result_state()
    presentations_by_mode = result_state.get("compare_presentations_by_mode", {})
    if mode is not None:
        return presentations_by_mode.get(mode)

    latest_mode = result_state.get("latest_mode")
    if latest_mode in presentations_by_mode:
        return presentations_by_mode.get(latest_mode)
    return result_state.get("compare_presentation")


def set_compare_presentation(
    *, compare_result, presentation, mode: str | None = None
) -> None:
    initialize_session_state()
    current = dict(_get_result_state())

    resolved_mode = _resolve_compare_mode(
        mode=mode,
        compare_result=compare_result,
        presentation=presentation,
    )

    results_by_mode = dict(current.get("compare_results_by_mode", {}))
    presentations_by_mode = dict(current.get("compare_presentations_by_mode", {}))
    errors_by_mode = dict(current.get("compare_errors_by_mode", {}))

    results_by_mode[resolved_mode] = compare_result
    presentations_by_mode[resolved_mode] = presentation
    errors_by_mode[resolved_mode] = None

    current.update(
        {
            "latest_mode": resolved_mode,
            "compare_result": compare_result,
            "compare_presentation": presentation,
            "compare_error": None,
            "compare_results_by_mode": results_by_mode,
            "compare_presentations_by_mode": presentations_by_mode,
            "compare_errors_by_mode": errors_by_mode,
        }
    )
    _session_state()[StateKey.RESULT_STATE] = current
    set_last_error_code(None)


def set_compare_error(error, *, mode: str | None = None) -> None:
    initialize_session_state()
    current = dict(_get_result_state())

    resolved_mode = _resolve_compare_mode(mode=mode, error=error)

    results_by_mode = dict(current.get("compare_results_by_mode", {}))
    presentations_by_mode = dict(current.get("compare_presentations_by_mode", {}))
    errors_by_mode = dict(current.get("compare_errors_by_mode", {}))
    errors_by_mode[resolved_mode] = error

    current.update(
        {
            "latest_mode": resolved_mode,
            "compare_result": results_by_mode.get(resolved_mode),
            "compare_presentation": presentations_by_mode.get(resolved_mode),
            "compare_error": error,
            "compare_results_by_mode": results_by_mode,
            "compare_presentations_by_mode": presentations_by_mode,
            "compare_errors_by_mode": errors_by_mode,
        }
    )
    _session_state()[StateKey.RESULT_STATE] = current
    set_last_error_code(getattr(error, "code", None))


def get_compare_error(mode: str | None = None):
    result_state = _get_result_state()
    errors_by_mode = result_state.get("compare_errors_by_mode", {})
    if mode is not None:
        return errors_by_mode.get(mode)

    latest_mode = result_state.get("latest_mode")
    if latest_mode in errors_by_mode:
        return errors_by_mode.get(latest_mode)
    return result_state.get("compare_error")


def get_latest_prediction_result(mode: str | None = None):
    result_state = _get_result_state()
    results_by_mode = result_state.get("prediction_results_by_mode", {})
    if mode is not None:
        return results_by_mode.get(mode)

    latest_mode = result_state.get("latest_prediction_mode")
    if latest_mode in results_by_mode:
        return results_by_mode.get(latest_mode)
    return result_state.get("prediction_result")


def set_prediction_result(result, *, mode: str | None = None) -> None:
    initialize_session_state()
    current = dict(_get_result_state())

    resolved_mode = _resolve_prediction_mode(mode=mode, result=result)

    results_by_mode = dict(current.get("prediction_results_by_mode", {}))
    errors_by_mode = dict(current.get("prediction_errors_by_mode", {}))
    results_by_mode[resolved_mode] = result
    errors_by_mode[resolved_mode] = None

    current.update(
        {
            "latest_prediction_mode": resolved_mode,
            "prediction_result": result,
            "prediction_error": None,
            "prediction_results_by_mode": results_by_mode,
            "prediction_errors_by_mode": errors_by_mode,
        }
    )
    _session_state()[StateKey.RESULT_STATE] = current
    set_last_error_code(None)


def set_prediction_error(error, *, mode: str | None = None) -> None:
    initialize_session_state()
    current = dict(_get_result_state())

    resolved_mode = _resolve_prediction_mode(mode=mode, error=error)

    results_by_mode = dict(current.get("prediction_results_by_mode", {}))
    errors_by_mode = dict(current.get("prediction_errors_by_mode", {}))
    errors_by_mode[resolved_mode] = error

    current.update(
        {
            "latest_prediction_mode": resolved_mode,
            "prediction_result": results_by_mode.get(resolved_mode),
            "prediction_error": error,
            "prediction_results_by_mode": results_by_mode,
            "prediction_errors_by_mode": errors_by_mode,
        }
    )
    _session_state()[StateKey.RESULT_STATE] = current
    set_last_error_code(getattr(error, "code", None))


def get_prediction_error(mode: str | None = None):
    result_state = _get_result_state()
    errors_by_mode = result_state.get("prediction_errors_by_mode", {})
    if mode is not None:
        return errors_by_mode.get(mode)

    latest_mode = result_state.get("latest_prediction_mode")
    if latest_mode in errors_by_mode:
        return errors_by_mode.get(latest_mode)
    return result_state.get("prediction_error")


def get_debug_mode() -> bool:
    initialize_session_state()
    return bool(_session_state()[StateKey.DEBUG_MODE])


def get_config_editor_state() -> dict[str, Any]:
    initialize_session_state()
    return _session_state()[StateKey.CONFIG_EDITOR_STATE]


def initialize_config_editor_draft(
    *,
    metrics_data: dict[str, Any],
    scoring_data: dict[str, Any],
    force: bool = False,
) -> None:
    initialize_session_state()
    current = deepcopy(get_config_editor_state())
    should_initialize = (
        force
        or current.get("draft_metrics_data") is None
        or current.get("draft_scoring_data") is None
    )
    if not should_initialize:
        _normalize_config_editor_selection(current)
        _session_state()[StateKey.CONFIG_EDITOR_STATE] = current
        return

    current = deepcopy(DEFAULT_CONFIG_EDITOR_STATE)
    current["loaded_metrics_data"] = deepcopy(metrics_data)
    current["loaded_scoring_data"] = deepcopy(scoring_data)
    current["draft_metrics_data"] = deepcopy(metrics_data)
    current["draft_scoring_data"] = deepcopy(scoring_data)
    _normalize_config_editor_selection(current)
    _session_state()[StateKey.CONFIG_EDITOR_STATE] = current


def set_config_editor_drafts(
    *,
    metrics_data: dict[str, Any] | None = None,
    scoring_data: dict[str, Any] | None = None,
) -> None:
    initialize_session_state()
    current = deepcopy(get_config_editor_state())
    if metrics_data is not None:
        current["draft_metrics_data"] = deepcopy(metrics_data)
    if scoring_data is not None:
        current["draft_scoring_data"] = deepcopy(scoring_data)
    current["dirty"] = _config_editor_dirty(current)
    current["validation_report"] = None
    current["save_status"] = None
    current["save_message"] = None
    current["save_error"] = None
    _normalize_config_editor_selection(current)
    _session_state()[StateKey.CONFIG_EDITOR_STATE] = current


def set_config_editor_selection(
    *,
    selected_metric_id: str | None = None,
    selected_profile_name: str | None = None,
) -> None:
    initialize_session_state()
    current = deepcopy(get_config_editor_state())
    if selected_metric_id is not None:
        current["selected_metric_id"] = selected_metric_id
    if selected_profile_name is not None:
        current["selected_profile_name"] = selected_profile_name
    _normalize_config_editor_selection(current)
    _session_state()[StateKey.CONFIG_EDITOR_STATE] = current


def set_config_editor_validation(
    report, *, against_dataset: bool | None = None
) -> None:
    initialize_session_state()
    current = deepcopy(get_config_editor_state())
    current["validation_report"] = report
    if against_dataset is not None:
        current["validation_against_dataset"] = bool(against_dataset)
    _session_state()[StateKey.CONFIG_EDITOR_STATE] = current


def set_config_editor_validation_preference(value: bool) -> None:
    initialize_session_state()
    current = deepcopy(get_config_editor_state())
    current["validation_against_dataset"] = bool(value)
    _session_state()[StateKey.CONFIG_EDITOR_STATE] = current


def set_config_editor_save_status(
    status: str | None, *, message: str | None = None, error=None
) -> None:
    initialize_session_state()
    current = deepcopy(get_config_editor_state())
    current["save_status"] = status
    current["save_message"] = message
    current["save_error"] = error
    _session_state()[StateKey.CONFIG_EDITOR_STATE] = current


def reset_config_editor_draft() -> None:
    initialize_session_state()
    current = deepcopy(get_config_editor_state())
    loaded_metrics = deepcopy(current.get("loaded_metrics_data"))
    loaded_scoring = deepcopy(current.get("loaded_scoring_data"))
    current["draft_metrics_data"] = loaded_metrics
    current["draft_scoring_data"] = loaded_scoring
    current["dirty"] = False
    current["validation_report"] = None
    current["save_status"] = None
    current["save_message"] = None
    current["save_error"] = None
    _normalize_config_editor_selection(current)
    _session_state()[StateKey.CONFIG_EDITOR_STATE] = current


def commit_config_editor_saved_state(
    *, metrics_data: dict[str, Any], scoring_data: dict[str, Any]
) -> None:
    initialize_session_state()
    current = deepcopy(get_config_editor_state())
    current["loaded_metrics_data"] = deepcopy(metrics_data)
    current["loaded_scoring_data"] = deepcopy(scoring_data)
    current["draft_metrics_data"] = deepcopy(metrics_data)
    current["draft_scoring_data"] = deepcopy(scoring_data)
    current["dirty"] = False
    current["validation_report"] = None
    current["save_status"] = None
    current["save_message"] = None
    current["save_error"] = None
    _normalize_config_editor_selection(current)
    _session_state()[StateKey.CONFIG_EDITOR_STATE] = current


def config_editor_is_dirty() -> bool:
    return bool(get_config_editor_state().get("dirty", False))


def _config_editor_dirty(state: dict[str, Any]) -> bool:
    return state.get("draft_metrics_data") != state.get(
        "loaded_metrics_data"
    ) or state.get("draft_scoring_data") != state.get("loaded_scoring_data")


def _normalize_config_editor_selection(state: dict[str, Any]) -> None:
    metrics_data = state.get("draft_metrics_data") or {"metrics": {}}
    scoring_data = state.get("draft_scoring_data") or {"profiles": {}}

    metric_ids = list((metrics_data.get("metrics") or {}).keys())
    profile_names = list((scoring_data.get("profiles") or {}).keys())

    selected_metric_id = state.get("selected_metric_id")
    if selected_metric_id not in metric_ids:
        state["selected_metric_id"] = metric_ids[0] if metric_ids else None

    selected_profile_name = state.get("selected_profile_name")
    if selected_profile_name not in profile_names:
        default_profile = scoring_data.get("default_profile")
        if default_profile in profile_names:
            state["selected_profile_name"] = default_profile
        else:
            state["selected_profile_name"] = profile_names[0] if profile_names else None
