from __future__ import annotations

import streamlit as st

from country_compare.config.models import YearStrategy
from country_compare.services import AppContext
from country_compare.services.errors import AppError
from country_compare.services.requests import SingleMetricRequest
from country_compare.ui.bootstrap import get_phase_b_services
from country_compare.ui.components.messages import render_app_error
from country_compare.ui.components.result_panels import render_single_metric_result
from country_compare.ui.components.selectors import (
    render_country_selector,
    render_single_metric_selector,
    render_target_year_input,
    render_year_strategy_selector,
)
from country_compare.ui.state import (
    get_debug_mode,
    get_latest_compare_presentation,
    get_selection_state,
    set_compare_error,
    set_compare_presentation,
    set_selection_state,
)


def _as_list(value):
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return list(value)


def render_compare_view(context: AppContext) -> None:
    st.title("Compare")
    st.caption("Read-only comparison flows. Single Metric is fully enabled in Phase B.")

    services = get_phase_b_services(context)
    dataset_service = services["dataset_service"]
    comparison_service = services["comparison_service"]
    presentation_service = services["presentation_service"]

    selection_state = get_selection_state()

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

    catalog_state = {
        "countries": _as_list(countries_catalog),
        "metrics": _as_list(metrics_catalog),
        "years": _as_list(years_catalog),
    }

    with st.container(border=True):
        st.markdown("### Shared selection")
        selected_countries = render_country_selector(
            catalog_state["countries"],
            default=selection_state.get("selected_countries", []),
        )
        year_strategy = render_year_strategy_selector(
            default=selection_state.get("year_strategy", YearStrategy.LATEST_PER_METRIC),
        )
        target_year = render_target_year_input(
            catalog_state["years"],
            enabled=(year_strategy == YearStrategy.TARGET_YEAR),
            default=selection_state.get("target_year"),
        )

    single_tab, multi_tab, weighted_tab = st.tabs(
        ["Single Metric", "Multi Metric", "Weighted Score"]
    )

    with single_tab:
        metric_id = render_single_metric_selector(
            catalog_state.get("metrics", []),
            default=selection_state.get("single_metric_id"),
        )
        run_clicked = st.button("Run comparison", type="primary", key="run_single_metric")

        set_selection_state(
            {
                "selected_countries": selected_countries,
                "year_strategy": year_strategy,
                "target_year": target_year,
                "single_metric_id": metric_id,
                "active_mode": "single_metric",
            }
        )

        if run_clicked:
            normalized_metric_id = str(metric_id).strip() if metric_id is not None else ""

            if not normalized_metric_id:
                set_compare_error(
                    AppError(
                        code="input_invalid",
                        title="Metric is required",
                        user_message="Please select a metric before running the comparison.",
                        technical_detail=f"metric_id={metric_id!r}",
                    )
                )
            elif len(selected_countries) < 2:
                set_compare_error(
                    AppError(
                        code="input_invalid",
                        title="Countries are required",
                        user_message="Please select at least two countries.",
                        technical_detail=f"selected_countries={selected_countries!r}",
                    )
                )
            else:
                request = SingleMetricRequest(
                    countries=selected_countries,
                    metric_id=normalized_metric_id,
                    year_strategy=year_strategy,
                    target_year=target_year,
                )
                compare_result = comparison_service.run_single_metric(request)
                if compare_result.ok:
                    presentation = presentation_service.build_single_metric_presentation(compare_result)
                    set_compare_presentation(compare_result=compare_result, presentation=presentation)
                    set_compare_error(None)
                else:
                    set_compare_error(compare_result.error)

        latest_presentation = get_latest_compare_presentation()
        render_single_metric_result(latest_presentation, debug=get_debug_mode())
        error = st.session_state.get("compare_error")
        if error is not None:
            render_app_error(error, debug=get_debug_mode())

    with multi_tab:
        st.info("Planned for Phase C. This tab is intentionally scaffolded only.")

    with weighted_tab:
        st.info("Planned for Phase C. This tab is intentionally scaffolded only.")
