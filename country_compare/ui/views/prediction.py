from __future__ import annotations

from typing import Any

import streamlit as st

from country_compare.services import AppContext
from country_compare.services.errors import AppError
from country_compare.ui.bootstrap import get_ui_services
from country_compare.ui.components.messages import render_app_error
from country_compare.ui.components.prediction_result_panels import (
    render_prediction_catalog_summary,
    render_prediction_service_result,
)
from country_compare.ui.components.selectors import (
    render_country_selector,
    render_country_single_selector,
    render_multi_metric_selector,
    render_positive_integer_input,
    render_prediction_method_selector,
    render_profile_selector,
    render_single_metric_selector,
)
from country_compare.ui.state import (
    get_debug_mode,
    get_latest_prediction_result,
    get_prediction_error,
    get_selection_state,
    set_catalog_state,
    set_prediction_error,
    set_prediction_result,
    set_selection_state,
)

MAX_FORECAST_HORIZON = 10
MAX_HOLDOUT_YEARS = 10


def render_prediction_view(context: AppContext) -> None:
    st.title("Prediction")
    st.caption(
        "Run forecast, predicted comparison, and backtest workflows through the service layer."
    )

    services = get_ui_services(context)
    dataset_service = services["dataset_service"]
    config_service = services["config_service"]
    prediction_service = services["prediction_service"]

    dataset_error = _get_dataset_availability_error(dataset_service)
    if dataset_error is not None:
        render_app_error(dataset_error, debug=get_debug_mode())
        st.info(
            "Prediction features become available once the canonical dataset can be loaded."
        )
        return

    countries_catalog = (
        dataset_service.get_country_catalog()
        if hasattr(dataset_service, "get_country_catalog")
        else dataset_service.list_countries()
    )
    metrics_catalog = (
        dataset_service.get_metric_catalog()
        if hasattr(dataset_service, "get_metric_catalog")
        else dataset_service.list_metrics()
    )
    years_catalog = dataset_service.list_years()

    try:
        profiles_catalog = config_service.get_profile_summaries()
    except Exception:
        profiles_catalog = []

    try:
        prediction_methods = list(prediction_service.list_prediction_methods())
    except Exception as exc:  # pragma: no cover - defensive service integration guard
        render_app_error(
            AppError(
                code="prediction_catalog_unavailable",
                title="Prediction catalog unavailable",
                user_message="Prediction methods could not be loaded from the service layer.",
                technical_detail=str(exc),
            ),
            debug=get_debug_mode(),
        )
        prediction_methods = []

    catalog_state = {
        "countries": list(countries_catalog or []),
        "metrics": list(metrics_catalog or []),
        "years": list(years_catalog or []),
        "profiles": list(profiles_catalog or []),
        "prediction_methods": prediction_methods,
    }
    set_catalog_state(catalog_state)

    _render_prediction_page_header(catalog_state)

    single_tab, multi_tab, comparison_tab, backtest_tab = st.tabs(
        [
            "Single Forecast",
            "Multi-Country Forecast",
            "Predicted Comparison",
            "Backtest",
        ]
    )

    with single_tab:
        _render_single_forecast_tab(catalog_state, prediction_service)

    with multi_tab:
        _render_multi_country_forecast_tab(catalog_state, prediction_service)

    with comparison_tab:
        _render_predicted_comparison_tab(catalog_state, prediction_service)

    with backtest_tab:
        _render_backtest_tab(catalog_state, prediction_service)


def _render_prediction_page_header(catalog_state: dict[str, Any]) -> None:
    methods = list(catalog_state.get("prediction_methods", []) or [])
    countries = list(catalog_state.get("countries", []) or [])
    metrics = list(catalog_state.get("metrics", []) or [])
    years = list(catalog_state.get("years", []) or [])

    cols = st.columns(4)
    cols[0].metric("Methods", len(methods))
    cols[1].metric("Countries", len(countries))
    cols[2].metric("Metrics", len(metrics))
    cols[3].metric(
        "Latest year",
        str(max(years)) if years else "—",
    )

    with st.expander("Prediction method catalog", expanded=False):
        render_prediction_catalog_summary(methods, debug=get_debug_mode())


def _render_single_forecast_tab(
    catalog_state: dict[str, Any], prediction_service
) -> None:
    selection_state = get_selection_state()

    with st.container(border=True):
        country_code = render_country_single_selector(
            catalog_state.get("countries", []),
            default=selection_state.get("prediction_country_code"),
            key="prediction_single_country_code",
        )
        metric_id = render_single_metric_selector(
            catalog_state.get("metrics", []),
            default=selection_state.get("prediction_metric_id"),
            key="prediction_single_metric_id",
        )
        method_id = render_prediction_method_selector(
            catalog_state.get("prediction_methods", []),
            default=selection_state.get("prediction_method"),
            key="prediction_single_method",
        )
        horizon_years = render_positive_integer_input(
            "Forecast horizon (years)",
            default=int(selection_state.get("prediction_horizon_years") or 3),
            min_value=1,
            max_value=MAX_FORECAST_HORIZON,
            key="prediction_single_horizon_years",
        )

        set_selection_state(
            {
                "prediction_active_mode": "single_forecast",
                "prediction_country_code": country_code or None,
                "prediction_metric_id": metric_id or None,
                "prediction_method": method_id
                or selection_state.get("prediction_method")
                or "linear_trend",
                "prediction_horizon_years": horizon_years,
            }
        )

        if st.button("Run single forecast", type="primary", key="run_single_forecast"):
            _run_single_forecast(
                prediction_service=prediction_service,
                country_code=country_code,
                metric_id=metric_id,
                method_id=method_id,
                horizon_years=horizon_years,
            )

    error = get_prediction_error(mode="single_forecast")
    if error is not None:
        render_app_error(error, debug=get_debug_mode())

    render_prediction_service_result(
        get_latest_prediction_result(mode="single_forecast"),
        debug=get_debug_mode(),
        empty_message="Run a single-country single-metric forecast to see results here.",
    )


def _render_multi_country_forecast_tab(
    catalog_state: dict[str, Any], prediction_service
) -> None:
    selection_state = get_selection_state()

    with st.container(border=True):
        country_codes = render_country_selector(
            catalog_state.get("countries", []),
            default=selection_state.get("prediction_country_codes", []),
            key="prediction_multi_country_codes",
        )
        metric_id = render_single_metric_selector(
            catalog_state.get("metrics", []),
            default=selection_state.get("prediction_metric_id"),
            key="prediction_multi_metric_id",
        )
        method_id = render_prediction_method_selector(
            catalog_state.get("prediction_methods", []),
            default=selection_state.get("prediction_method"),
            key="prediction_multi_method",
        )
        horizon_years = render_positive_integer_input(
            "Forecast horizon (years)",
            default=int(selection_state.get("prediction_horizon_years") or 3),
            min_value=1,
            max_value=MAX_FORECAST_HORIZON,
            key="prediction_multi_horizon_years",
        )

        set_selection_state(
            {
                "prediction_active_mode": "multi_country_forecast",
                "prediction_country_codes": list(country_codes),
                "prediction_metric_id": metric_id or None,
                "prediction_method": method_id
                or selection_state.get("prediction_method")
                or "linear_trend",
                "prediction_horizon_years": horizon_years,
            }
        )

        if st.button(
            "Run multi-country forecast",
            type="primary",
            key="run_multi_country_forecast",
        ):
            _run_multi_country_forecast(
                prediction_service=prediction_service,
                country_codes=country_codes,
                metric_id=metric_id,
                method_id=method_id,
                horizon_years=horizon_years,
            )

    error = get_prediction_error(mode="multi_country_forecast")
    if error is not None:
        render_app_error(error, debug=get_debug_mode())

    render_prediction_service_result(
        get_latest_prediction_result(mode="multi_country_forecast"),
        debug=get_debug_mode(),
        empty_message="Run a multi-country forecast to see batch results here.",
    )


def _render_predicted_comparison_tab(
    catalog_state: dict[str, Any], prediction_service
) -> None:
    selection_state = get_selection_state()
    comparison_modes = [
        ("Single Metric", "predicted_single_metric_comparison"),
        ("Multi Metric", "predicted_multi_metric_comparison"),
        ("Profile", "predicted_profile_comparison"),
    ]
    labels = [label for label, _ in comparison_modes]
    values = {label: value for label, value in comparison_modes}

    default_mode = selection_state.get("prediction_active_mode")
    default_label = next(
        (label for label, value in comparison_modes if value == default_mode),
        "Single Metric",
    )

    with st.container(border=True):
        selected_label = st.radio(
            "Comparison type",
            options=labels,
            horizontal=True,
            index=labels.index(default_label),
            key="prediction_comparison_type",
        )
        selected_mode = values[selected_label]

        country_codes = render_country_selector(
            catalog_state.get("countries", []),
            default=selection_state.get("prediction_country_codes", []),
            key="prediction_compare_country_codes",
        )
        method_id = render_prediction_method_selector(
            catalog_state.get("prediction_methods", []),
            default=selection_state.get("prediction_method"),
            key="prediction_compare_method",
        )
        horizon_years = render_positive_integer_input(
            "Forecast horizon (years)",
            default=int(selection_state.get("prediction_horizon_years") or 3),
            min_value=1,
            max_value=MAX_FORECAST_HORIZON,
            key="prediction_compare_horizon_years",
        )

        selection_mode = st.radio(
            "Select forecast by",
            options=["Horizon", "Year"],
            horizontal=True,
            index=0 if selection_state.get("prediction_forecast_year") is None else 1,
            key="prediction_compare_forecast_selection_mode",
        )

        forecast_horizon = None
        forecast_year = None
        if selection_mode == "Horizon":
            forecast_horizon = render_positive_integer_input(
                "Forecast horizon to compare",
                default=int(selection_state.get("prediction_forecast_horizon") or 1),
                min_value=1,
                max_value=horizon_years,
                key="prediction_compare_forecast_horizon",
            )
        else:
            years = list(catalog_state.get("years", []) or [])
            latest_year = int(max(years)) if years else 2000
            forecast_year = render_positive_integer_input(
                "Forecast year to compare",
                default=int(
                    selection_state.get("prediction_forecast_year") or latest_year + 1
                ),
                min_value=latest_year + 1 if years else 1,
                max_value=latest_year + horizon_years if years else None,
                key="prediction_compare_forecast_year",
            )

        metric_id = ""
        metric_ids: list[str] = []
        profile_name = ""
        if selected_mode == "predicted_single_metric_comparison":
            metric_id = render_single_metric_selector(
                catalog_state.get("metrics", []),
                default=selection_state.get("prediction_metric_id"),
                key="prediction_compare_metric_id",
            )
        elif selected_mode == "predicted_multi_metric_comparison":
            metric_ids = render_multi_metric_selector(
                catalog_state.get("metrics", []),
                default=selection_state.get("prediction_metric_ids", []),
                key="prediction_compare_metric_ids",
            )
        else:
            profile_name = render_profile_selector(
                catalog_state.get("profiles", []),
                default=selection_state.get("prediction_profile_name"),
                key="prediction_compare_profile_name",
            )

        set_selection_state(
            {
                "prediction_active_mode": selected_mode,
                "prediction_country_codes": list(country_codes),
                "prediction_metric_id": metric_id
                or selection_state.get("prediction_metric_id"),
                "prediction_metric_ids": list(metric_ids),
                "prediction_profile_name": profile_name or None,
                "prediction_method": method_id
                or selection_state.get("prediction_method")
                or "linear_trend",
                "prediction_horizon_years": horizon_years,
                "prediction_forecast_horizon": forecast_horizon,
                "prediction_forecast_year": forecast_year,
            }
        )

        if st.button(
            "Run predicted comparison", type="primary", key="run_predicted_comparison"
        ):
            _run_predicted_comparison(
                prediction_service=prediction_service,
                mode=selected_mode,
                country_codes=country_codes,
                metric_id=metric_id,
                metric_ids=metric_ids,
                profile_name=profile_name,
                method_id=method_id,
                horizon_years=horizon_years,
                forecast_horizon=forecast_horizon,
                forecast_year=forecast_year,
            )

    error = get_prediction_error(
        mode=get_selection_state().get("prediction_active_mode")
    )
    if error is not None:
        render_app_error(error, debug=get_debug_mode())

    render_prediction_service_result(
        get_latest_prediction_result(
            mode=get_selection_state().get("prediction_active_mode")
        ),
        debug=get_debug_mode(),
        empty_message="Run a predicted comparison to see ranking output here.",
    )


def _render_backtest_tab(catalog_state: dict[str, Any], prediction_service) -> None:
    selection_state = get_selection_state()

    with st.container(border=True):
        country_code = render_country_single_selector(
            catalog_state.get("countries", []),
            default=selection_state.get("prediction_country_code"),
            key="prediction_backtest_country_code",
        )
        metric_id = render_single_metric_selector(
            catalog_state.get("metrics", []),
            default=selection_state.get("prediction_metric_id"),
            key="prediction_backtest_metric_id",
        )
        method_id = render_prediction_method_selector(
            catalog_state.get("prediction_methods", []),
            default=selection_state.get("prediction_method"),
            key="prediction_backtest_method",
        )
        holdout_years = render_positive_integer_input(
            "Holdout years",
            default=int(selection_state.get("prediction_holdout_years") or 2),
            min_value=1,
            max_value=MAX_HOLDOUT_YEARS,
            key="prediction_backtest_holdout_years",
        )

        set_selection_state(
            {
                "prediction_active_mode": "backtest",
                "prediction_country_code": country_code or None,
                "prediction_metric_id": metric_id or None,
                "prediction_method": method_id
                or selection_state.get("prediction_method")
                or "linear_trend",
                "prediction_holdout_years": holdout_years,
            }
        )

        if st.button("Run backtest", type="primary", key="run_backtest"):
            _run_backtest(
                prediction_service=prediction_service,
                country_code=country_code,
                metric_id=metric_id,
                method_id=method_id,
                holdout_years=holdout_years,
            )

    error = get_prediction_error(mode="backtest")
    if error is not None:
        render_app_error(error, debug=get_debug_mode())

    render_prediction_service_result(
        get_latest_prediction_result(mode="backtest"),
        debug=get_debug_mode(),
        empty_message="Run a holdout backtest to see evaluation metrics here.",
    )


def _run_single_forecast(
    *,
    prediction_service,
    country_code: str,
    metric_id: str,
    method_id: str,
    horizon_years: int,
) -> None:
    result = prediction_service.run_single_metric_prediction(
        country_code=country_code,
        metric_id=metric_id,
        method=method_id,
        horizon_years=int(horizon_years),
    )
    _store_prediction_service_result(result, mode="single_forecast")


def _run_multi_country_forecast(
    *,
    prediction_service,
    country_codes: list[str],
    metric_id: str,
    method_id: str,
    horizon_years: int,
) -> None:
    result = prediction_service.run_single_metric_prediction_for_countries(
        metric_id=metric_id,
        country_codes=list(country_codes),
        method=method_id,
        horizon_years=int(horizon_years),
        fail_fast=False,
    )
    _store_prediction_service_result(result, mode="multi_country_forecast")


def _run_predicted_comparison(
    *,
    prediction_service,
    mode: str,
    country_codes: list[str],
    metric_id: str,
    metric_ids: list[str],
    profile_name: str,
    method_id: str,
    horizon_years: int,
    forecast_horizon: int | None,
    forecast_year: int | None,
) -> None:
    if mode == "predicted_single_metric_comparison":
        result = prediction_service.run_predicted_single_metric_comparison(
            metric_id=metric_id,
            country_codes=list(country_codes),
            method=method_id,
            horizon_years=int(horizon_years),
            forecast_horizon=forecast_horizon,
            forecast_year=forecast_year,
        )
    elif mode == "predicted_multi_metric_comparison":
        result = prediction_service.run_predicted_multi_metric_comparison(
            metric_ids=list(metric_ids),
            country_codes=list(country_codes),
            method=method_id,
            horizon_years=int(horizon_years),
            forecast_horizon=forecast_horizon,
            forecast_year=forecast_year,
        )
    else:
        result = prediction_service.run_predicted_profile_comparison(
            profile_name=profile_name,
            country_codes=list(country_codes),
            method=method_id,
            horizon_years=int(horizon_years),
            forecast_horizon=forecast_horizon,
            forecast_year=forecast_year,
        )
    _store_prediction_service_result(result, mode=mode)


def _run_backtest(
    *,
    prediction_service,
    country_code: str,
    metric_id: str,
    method_id: str,
    holdout_years: int,
) -> None:
    result = prediction_service.run_backtest(
        country_code=country_code,
        metric_id=metric_id,
        method=method_id,
        holdout_years=int(holdout_years),
    )
    _store_prediction_service_result(result, mode="backtest")


def _store_prediction_service_result(result, *, mode: str) -> None:
    if getattr(result, "ok", False):
        set_prediction_result(result, mode=mode)
        set_prediction_error(None, mode=mode)
    else:
        set_prediction_error(getattr(result, "error", None), mode=mode)


def _get_dataset_availability_error(dataset_service) -> AppError | None:
    summary = None
    if hasattr(dataset_service, "get_dataset_summary"):
        try:
            summary = dataset_service.get_dataset_summary()
        except Exception:
            summary = None

    if summary is not None and getattr(summary, "error", None) is not None:
        return summary.error

    return None
