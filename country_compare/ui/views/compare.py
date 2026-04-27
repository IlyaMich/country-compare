from __future__ import annotations

from collections.abc import Iterable
from typing import Any, cast

import streamlit as st

from country_compare.config.models import YearStrategy
from country_compare.services import AppContext
from country_compare.services.errors import AppError
from country_compare.services.requests import (
    MultiMetricRequest,
    SingleMetricRequest,
    WeightedScoreRequest,
)
from country_compare.ui import query_state
from country_compare.ui.bootstrap import get_ui_services
from country_compare.ui.components.messages import render_app_error
from country_compare.ui.components.result_panels import render_comparison_result
from country_compare.ui.components.selectors import (
    render_country_selector,
    render_multi_metric_selector,
    render_profile_selector,
    render_single_metric_selector,
    render_target_year_input,
    render_year_strategy_selector,
)
from country_compare.ui.state import (
    get_compare_error,
    get_debug_mode,
    get_latest_compare_presentation,
    get_selection_state,
    set_catalog_state,
    set_compare_error,
    set_compare_presentation,
    set_selection_state,
)


def _as_list(value: Iterable[Any] | None) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return list(value)


def render_compare_view(context: AppContext) -> None:
    st.title("Compare")
    st.caption("Run single-metric, multi-metric, and weighted-score comparisons.")

    services = get_ui_services(context)
    dataset_service = cast(Any, services["dataset_service"])
    config_service = cast(Any, services["config_service"])
    comparison_service = cast(Any, services["comparison_service"])
    presentation_service = cast(Any, services["presentation_service"])

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

    try:
        profiles_catalog = config_service.get_profile_summaries()
    except Exception:
        profiles_catalog = []

    catalog_state = {
        "countries": _as_list(countries_catalog),
        "metrics": _as_list(metrics_catalog),
        "years": _as_list(years_catalog),
        "profiles": _as_list(profiles_catalog),
    }
    set_catalog_state(catalog_state)

    with st.container(border=True):
        st.markdown("### Shared selection")
        selected_countries = render_country_selector(
            catalog_state["countries"],
            default=selection_state.get("selected_countries", []),
        )
        year_strategy = render_year_strategy_selector(
            default=selection_state.get(
                "year_strategy", YearStrategy.LATEST_PER_METRIC
            ),
        )
        target_year = render_target_year_input(
            catalog_state["years"],
            enabled=(year_strategy == YearStrategy.TARGET_YEAR),
            default=selection_state.get("target_year"),
        )

    set_selection_state(
        {
            "selected_countries": selected_countries,
            "year_strategy": year_strategy.value,
            "target_year": target_year,
        }
    )

    single_tab, multi_tab, weighted_tab = st.tabs(
        ["Single Metric", "Multi Metric", "Weighted Score"]
    )

    with single_tab:
        metric_id = render_single_metric_selector(
            catalog_state.get("metrics", []),
            default=selection_state.get("single_metric_id"),
        )
        set_selection_state({"single_metric_id": metric_id})

        if st.button(
            "Run single-metric comparison", type="primary", key="run_single_metric"
        ):
            set_selection_state({"active_mode": "single_metric"})
            _run_single_metric_flow(
                selected_countries=selected_countries,
                metric_id=metric_id,
                year_strategy=year_strategy,
                target_year=target_year,
                comparison_service=comparison_service,
                presentation_service=presentation_service,
            )

        latest_presentation = get_latest_compare_presentation(mode="single_metric")
        render_comparison_result(
            latest_presentation,
            debug=get_debug_mode(),
            presentation_service=presentation_service,
            empty_message="Run a single-metric comparison to see results here.",
        )
        error = get_compare_error(mode="single_metric")
        if error is not None:
            render_app_error(error, debug=get_debug_mode())

    with multi_tab:
        metric_ids = render_multi_metric_selector(
            catalog_state.get("metrics", []),
            default=selection_state.get("multi_metric_ids", []),
        )
        set_selection_state({"multi_metric_ids": metric_ids})

        if st.button(
            "Run multi-metric comparison", type="primary", key="run_multi_metric"
        ):
            set_selection_state({"active_mode": "multi_metric"})
            _run_multi_metric_flow(
                selected_countries=selected_countries,
                metric_ids=metric_ids,
                year_strategy=year_strategy,
                target_year=target_year,
                comparison_service=comparison_service,
                presentation_service=presentation_service,
            )

        latest_presentation = get_latest_compare_presentation(mode="multi_metric")
        render_comparison_result(
            latest_presentation,
            debug=get_debug_mode(),
            presentation_service=presentation_service,
            empty_message="Run a multi-metric comparison to see results here.",
        )
        error = get_compare_error(mode="multi_metric")
        if error is not None:
            render_app_error(error, debug=get_debug_mode())

    with weighted_tab:
        profile_name = render_profile_selector(
            catalog_state.get("profiles", []),
            default=selection_state.get("weighted_profile_name"),
        )
        set_selection_state({"weighted_profile_name": profile_name})

        if st.button(
            "Run weighted-score comparison", type="primary", key="run_weighted_score"
        ):
            set_selection_state({"active_mode": "weighted_score"})
            _run_weighted_score_flow(
                selected_countries=selected_countries,
                profile_name=profile_name,
                target_year=target_year,
                comparison_service=comparison_service,
                presentation_service=presentation_service,
            )

        latest_presentation = get_latest_compare_presentation(mode="weighted_score")
        render_comparison_result(
            latest_presentation,
            debug=get_debug_mode(),
            presentation_service=presentation_service,
            empty_message="Run a weighted-score comparison to see results here.",
        )
        error = get_compare_error(mode="weighted_score")
        if error is not None:
            render_app_error(error, debug=get_debug_mode())

    query_state.sync_query_params_from_state(
        selected_page="Compare",
        selection_state=get_selection_state(),
    )


def _run_single_metric_flow(
    *,
    selected_countries: list[str],
    metric_id: str,
    year_strategy: YearStrategy,
    target_year: int | None,
    comparison_service,
    presentation_service,
) -> None:
    normalized_metric_id = str(metric_id).strip() if metric_id is not None else ""

    if not normalized_metric_id:
        set_compare_error(
            AppError(
                code="input_invalid",
                title="Metric is required",
                user_message="Please select a metric before running the comparison.",
                technical_detail=f"metric_id={metric_id!r}",
            ),
            mode="single_metric",
        )
        return

    if len(selected_countries) < 2:
        set_compare_error(
            AppError(
                code="input_invalid",
                title="Countries are required",
                user_message="Please select at least two countries.",
                technical_detail=f"selected_countries={selected_countries!r}",
            ),
            mode="single_metric",
        )
        return

    request = SingleMetricRequest(
        countries=selected_countries,
        metric_id=normalized_metric_id,
        year_strategy=year_strategy,
        target_year=target_year,
    )
    compare_result = comparison_service.run_single_metric(request)
    if compare_result.ok:
        presentation = presentation_service.build_single_metric_presentation(
            compare_result
        )
        set_compare_presentation(
            compare_result=compare_result,
            presentation=presentation,
            mode="single_metric",
        )
        set_compare_error(None, mode="single_metric")
    else:
        set_compare_error(compare_result.error, mode="single_metric")


def _run_multi_metric_flow(
    *,
    selected_countries: list[str],
    metric_ids: list[str],
    year_strategy: YearStrategy,
    target_year: int | None,
    comparison_service,
    presentation_service,
) -> None:
    if len(selected_countries) < 2:
        set_compare_error(
            AppError(
                code="input_invalid",
                title="Countries are required",
                user_message="Please select at least two countries.",
                technical_detail=f"selected_countries={selected_countries!r}",
            ),
            mode="multi_metric",
        )
        return

    if not metric_ids:
        set_compare_error(
            AppError(
                code="input_invalid",
                title="Metrics are required",
                user_message="Please select at least one metric before running the comparison.",
                technical_detail=f"metric_ids={metric_ids!r}",
            ),
            mode="multi_metric",
        )
        return

    request = MultiMetricRequest(
        countries=selected_countries,
        metric_ids=metric_ids,
        year_strategy=year_strategy,
        target_year=target_year,
    )
    compare_result = comparison_service.run_multi_metric(request)
    if compare_result.ok:
        presentation = presentation_service.build_multi_metric_presentation(
            compare_result
        )
        set_compare_presentation(
            compare_result=compare_result,
            presentation=presentation,
            mode="multi_metric",
        )
        set_compare_error(None, mode="multi_metric")
    else:
        set_compare_error(compare_result.error, mode="multi_metric")


def _run_weighted_score_flow(
    *,
    selected_countries: list[str],
    profile_name: str,
    target_year: int | None,
    comparison_service,
    presentation_service,
) -> None:
    normalized_profile_name = (
        str(profile_name).strip() if profile_name is not None else ""
    )

    if len(selected_countries) < 2:
        set_compare_error(
            AppError(
                code="input_invalid",
                title="Countries are required",
                user_message="Please select at least two countries.",
                technical_detail=f"selected_countries={selected_countries!r}",
            ),
            mode="weighted_score",
        )
        return

    if not normalized_profile_name:
        set_compare_error(
            AppError(
                code="input_invalid",
                title="Profile is required",
                user_message="Please select a scoring profile before running the comparison.",
                technical_detail=f"profile_name={profile_name!r}",
            ),
            mode="weighted_score",
        )
        return

    request = WeightedScoreRequest(
        countries=selected_countries,
        profile_name=normalized_profile_name,
        target_year=target_year,
    )
    compare_result = comparison_service.run_weighted_score(request)
    if compare_result.ok:
        presentation = presentation_service.build_weighted_score_presentation(
            compare_result
        )
        set_compare_presentation(
            compare_result=compare_result,
            presentation=presentation,
            mode="weighted_score",
        )
        set_compare_error(None, mode="weighted_score")
    else:
        set_compare_error(compare_result.error, mode="weighted_score")
