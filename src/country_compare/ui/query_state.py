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

PREDICTION_MODE_PARAM = "prediction_mode"
PREDICTION_COUNTRY_PARAM = "prediction_country"
PREDICTION_COUNTRIES_PARAM = "prediction_countries"
PREDICTION_METRIC_PARAM = "prediction_metric"
PREDICTION_METRICS_PARAM = "prediction_metrics"
PREDICTION_PROFILE_PARAM = "prediction_profile"
PREDICTION_METHOD_PARAM = "prediction_method"
PREDICTION_HORIZON_YEARS_PARAM = "prediction_horizon_years"
PREDICTION_FORECAST_YEAR_PARAM = "prediction_forecast_year"
PREDICTION_FORECAST_HORIZON_PARAM = "prediction_forecast_horizon"
PREDICTION_HOLDOUT_YEARS_PARAM = "prediction_holdout_years"

VALID_COMPARE_MODES = {"single_metric", "multi_metric", "weighted_score"}
VALID_PREDICTION_MODES = {
    "single_forecast",
    "multi_country_forecast",
    "predicted_single_metric_comparison",
    "predicted_multi_metric_comparison",
    "predicted_profile_comparison",
    "backtest",
}

QUERY_STATE_INITIALIZED_KEY = "country_compare.query_state_initialized"


def build_selection_state_from_query_params(
    params: Mapping[str, Any],
    *,
    selected_page: str = "Compare",
) -> dict[str, Any]:
    if selected_page == "Prediction":
        return build_prediction_selection_state_from_query_params(params)
    return build_compare_selection_state_from_query_params(params)


def build_compare_selection_state_from_query_params(
    params: Mapping[str, Any],
) -> dict[str, Any]:
    active_mode = _coerce_compare_mode(_first_value(params.get(MODE_PARAM)))
    year_strategy = _coerce_year_strategy(_first_value(params.get(YEAR_STRATEGY_PARAM)))
    target_year = _coerce_int(_first_value(params.get(TARGET_YEAR_PARAM)))

    return {
        "active_mode": active_mode,
        "selected_countries": _split_csv_codes(
            _first_value(params.get(COUNTRIES_PARAM))
        ),
        "single_metric_id": _clean_text(_first_value(params.get(SINGLE_METRIC_PARAM)))
        or None,
        "multi_metric_ids": _split_csv_values(
            _first_value(params.get(MULTI_METRICS_PARAM))
        ),
        "weighted_profile_name": _clean_text(_first_value(params.get(PROFILE_PARAM)))
        or None,
        "year_strategy": year_strategy.value,
        "target_year": target_year,
    }


def build_prediction_selection_state_from_query_params(
    params: Mapping[str, Any],
) -> dict[str, Any]:
    prediction_mode = _coerce_prediction_mode(
        _first_value(params.get(PREDICTION_MODE_PARAM))
    )
    prediction_country = (
        _clean_text(_first_value(params.get(PREDICTION_COUNTRY_PARAM))).upper() or None
    )
    prediction_countries = _split_csv_codes(
        _first_value(params.get(PREDICTION_COUNTRIES_PARAM))
    )
    prediction_metric = (
        _clean_text(_first_value(params.get(PREDICTION_METRIC_PARAM))) or None
    )
    prediction_metrics = _split_csv_values(
        _first_value(params.get(PREDICTION_METRICS_PARAM))
    )
    prediction_profile = (
        _clean_text(_first_value(params.get(PREDICTION_PROFILE_PARAM))) or None
    )
    prediction_method = (
        _clean_text(_first_value(params.get(PREDICTION_METHOD_PARAM))) or "linear_trend"
    )
    prediction_horizon_years = (
        _coerce_int(_first_value(params.get(PREDICTION_HORIZON_YEARS_PARAM))) or 3
    )
    prediction_forecast_year = _coerce_int(
        _first_value(params.get(PREDICTION_FORECAST_YEAR_PARAM))
    )
    prediction_forecast_horizon = (
        _coerce_int(_first_value(params.get(PREDICTION_FORECAST_HORIZON_PARAM))) or 1
    )
    prediction_holdout_years = (
        _coerce_int(_first_value(params.get(PREDICTION_HOLDOUT_YEARS_PARAM))) or 2
    )

    return {
        "prediction_active_mode": prediction_mode,
        "prediction_country_code": prediction_country,
        "prediction_country_codes": prediction_countries,
        "prediction_metric_id": prediction_metric,
        "prediction_metric_ids": prediction_metrics,
        "prediction_profile_name": prediction_profile,
        "prediction_method": prediction_method,
        "prediction_horizon_years": prediction_horizon_years,
        "prediction_forecast_year": prediction_forecast_year,
        "prediction_forecast_horizon": prediction_forecast_horizon,
        "prediction_holdout_years": prediction_holdout_years,
    }


def build_query_params(
    *, selected_page: str, selection_state: Mapping[str, Any]
) -> dict[str, str]:
    params: dict[str, str] = {PAGE_PARAM: str(selected_page)}
    if str(selected_page) == "Compare":
        params.update(build_compare_query_params(selection_state=selection_state))
    elif str(selected_page) == "Prediction":
        params.update(build_prediction_query_params(selection_state=selection_state))
    return params


def build_compare_query_params(*, selection_state: Mapping[str, Any]) -> dict[str, str]:
    params: dict[str, str] = {}
    active_mode = _coerce_compare_mode(selection_state.get("active_mode"))
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


def build_prediction_query_params(
    *, selection_state: Mapping[str, Any]
) -> dict[str, str]:
    params: dict[str, str] = {}
    prediction_mode = _coerce_prediction_mode(
        selection_state.get("prediction_active_mode")
    )
    prediction_country_code = _clean_text(
        selection_state.get("prediction_country_code")
    ).upper()
    prediction_country_codes = _split_csv_codes(
        selection_state.get("prediction_country_codes")
    )
    prediction_metric_id = _clean_text(selection_state.get("prediction_metric_id"))
    prediction_metric_ids = _split_csv_values(
        selection_state.get("prediction_metric_ids")
    )
    prediction_profile_name = _clean_text(
        selection_state.get("prediction_profile_name")
    )
    prediction_method = (
        _clean_text(selection_state.get("prediction_method")) or "linear_trend"
    )
    prediction_horizon_years = (
        _coerce_int(selection_state.get("prediction_horizon_years")) or 3
    )
    prediction_forecast_year = _coerce_int(
        selection_state.get("prediction_forecast_year")
    )
    prediction_forecast_horizon = _coerce_int(
        selection_state.get("prediction_forecast_horizon")
    )
    prediction_holdout_years = (
        _coerce_int(selection_state.get("prediction_holdout_years")) or 2
    )

    params[PREDICTION_MODE_PARAM] = prediction_mode
    params[PREDICTION_METHOD_PARAM] = prediction_method
    params[PREDICTION_HORIZON_YEARS_PARAM] = str(prediction_horizon_years)

    if prediction_country_code:
        params[PREDICTION_COUNTRY_PARAM] = prediction_country_code
    if prediction_country_codes:
        params[PREDICTION_COUNTRIES_PARAM] = ",".join(prediction_country_codes)
    if prediction_metric_id:
        params[PREDICTION_METRIC_PARAM] = prediction_metric_id
    if prediction_metric_ids:
        params[PREDICTION_METRICS_PARAM] = ",".join(prediction_metric_ids)
    if prediction_profile_name:
        params[PREDICTION_PROFILE_PARAM] = prediction_profile_name
    if prediction_forecast_year is not None:
        params[PREDICTION_FORECAST_YEAR_PARAM] = str(prediction_forecast_year)
    if prediction_forecast_horizon is not None:
        params[PREDICTION_FORECAST_HORIZON_PARAM] = str(prediction_forecast_horizon)
    if prediction_mode == "backtest":
        params[PREDICTION_HOLDOUT_YEARS_PARAM] = str(prediction_holdout_years)

    return params


def apply_query_params_once() -> None:
    state.initialize_session_state()
    if _query_state_initialized():
        return

    raw_params = {key: value for key, value in st.query_params.items()}
    selected_page = _coerce_page(_first_value(raw_params.get(PAGE_PARAM)))
    state.set_selected_page(selected_page)

    if selected_page == "Compare":
        state.set_selection_state(
            build_compare_selection_state_from_query_params(raw_params)
        )
    elif selected_page == "Prediction":
        state.set_selection_state(
            build_prediction_selection_state_from_query_params(raw_params)
        )

    _mark_query_state_initialized(True)


def sync_query_params_from_state(
    *, selected_page: str, selection_state: Mapping[str, Any]
) -> None:
    target = build_query_params(
        selected_page=selected_page, selection_state=selection_state
    )
    current = {key: _first_value(value) for key, value in st.query_params.items()}
    if current == target:
        return

    st.query_params.clear()
    for key, value in target.items():
        st.query_params[key] = value


def _coerce_page(value: Any) -> str:
    text = _clean_text(value)
    if text in {"Overview", "Compare", "Prediction", "Config Editor"}:
        return text
    return "Overview"


def _coerce_compare_mode(value: Any) -> str:
    text = _clean_text(value)
    return text if text in VALID_COMPARE_MODES else "single_metric"


def _coerce_prediction_mode(value: Any) -> str:
    text = _clean_text(value)
    return text if text in VALID_PREDICTION_MODES else "single_forecast"


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


def _query_state_initialized() -> bool:
    legacy = getattr(state, "query_state_initialized", None)
    if callable(legacy):
        try:
            return bool(legacy())
        except Exception:
            pass
    return bool(st.session_state.get(QUERY_STATE_INITIALIZED_KEY, False))


def _mark_query_state_initialized(value: bool = True) -> None:
    legacy = getattr(state, "mark_query_state_initialized", None)
    if callable(legacy):
        try:
            legacy(value)
            return
        except Exception:
            pass
    st.session_state[QUERY_STATE_INITIALIZED_KEY] = bool(value)
