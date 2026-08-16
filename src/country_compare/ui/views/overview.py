from __future__ import annotations

import pandas as pd
import streamlit as st

from country_compare.clients.base import CountryCompareClient
from country_compare.clients.errors import (
    ClientBackendError,
    ClientConnectionError,
    ClientResponseError,
)
from country_compare.services import AppError
from country_compare.services.models import ConfigStatus, DatasetSummary
from country_compare.ui.runtime import UiRuntimeContext


def render_page(runtime: UiRuntimeContext, *, debug: bool = False) -> None:
    st.title("Country Comparison — Overview")
    st.caption("Dataset and configuration inspection.")

    validate_against_dataset = st.checkbox(
        "Validate config against current dataset",
        value=False,
        help="Runs the optional metrics-vs-dataset consistency check from the config layer.",
    )

    client = runtime.client

    try:
        overview = client.get_overview_status(
            validate_config_against_dataset=validate_against_dataset,
        )
    except (
        ClientConnectionError,
        ClientResponseError,
        ClientBackendError,
    ) as exc:
        _render_error(exc.error, debug=debug)
        return

    for warning in overview.warnings:
        st.info(warning)

    st.subheader("Dataset status")
    _render_dataset_section(
        overview.dataset,
        client=client,
        debug=debug,
    )

    st.divider()

    st.subheader("Configuration status")
    _render_config_section(overview.config, debug=debug)

    st.divider()

    st.subheader("Next steps")
    st.write(
        "Use the comparison and prediction pages to explore the current "
        "dataset through the configured Country Compare runtime."
    )


def _render_dataset_section(
    dataset: DatasetSummary,
    *,
    client: CountryCompareClient,
    debug: bool,
) -> None:
    backend_col, path_col = st.columns([1, 3])
    backend_col.metric("Backend", dataset.backend)
    path_col.text_input(
        "Dataset path",
        value=dataset.dataset_path or "(not resolved)",
        disabled=True,
    )

    if dataset.error is not None:
        _render_error(dataset.error, debug=debug)
        return

    st.success("Dataset is available.")

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Rows", dataset.row_count)
    col2.metric("Countries", dataset.country_count)
    col3.metric("Metrics", dataset.metric_count)
    col4.metric(
        "Year range",
        (
            f"{dataset.year_min}–{dataset.year_max}"
            if dataset.year_min is not None and dataset.year_max is not None
            else "N/A"
        ),
    )

    if dataset.categories:
        category_df = pd.DataFrame(
            [
                {
                    "category": item.name,
                    "rows": item.row_count,
                    "countries": item.country_count,
                    "metrics": item.metric_count,
                }
                for item in dataset.categories
            ]
        )
        st.write("**Category breakdown**")
        st.dataframe(
            category_df,
            use_container_width=True,
            hide_index=True,
        )

    with st.expander("Available countries", expanded=False):
        try:
            countries = client.list_countries()
        except (
            ClientConnectionError,
            ClientResponseError,
            ClientBackendError,
        ) as exc:
            _render_error(exc.error, debug=debug)
        else:
            if not countries:
                st.write("No countries found.")
            else:
                st.dataframe(
                    pd.DataFrame(
                        [
                            {
                                "country_code": item.code,
                                "country_name": item.name,
                            }
                            for item in countries
                        ]
                    ),
                    use_container_width=True,
                    hide_index=True,
                )

    with st.expander("Available metrics", expanded=False):
        try:
            metrics = client.list_metrics()
        except (
            ClientConnectionError,
            ClientResponseError,
            ClientBackendError,
        ) as exc:
            _render_error(exc.error, debug=debug)
        else:
            if not metrics:
                st.write("No metrics found.")
            else:
                st.dataframe(
                    pd.DataFrame(
                        [
                            {
                                "metric_id": item.metric_id,
                                "display_name": item.display_name,
                                "category": item.category,
                                "unit": item.unit,
                            }
                            for item in metrics
                        ]
                    ),
                    use_container_width=True,
                    hide_index=True,
                )


def _render_config_section(
    config: ConfigStatus,
    *,
    debug: bool,
) -> None:
    path_col1, path_col2 = st.columns(2)
    path_col1.text_input(
        "Metrics config",
        value=config.metrics_config_path,
        disabled=True,
    )
    path_col2.text_input(
        "Scoring config",
        value=config.scoring_config_path,
        disabled=True,
    )

    if config.error is not None:
        _render_error(config.error, debug=debug)
        return

    st.success("Configuration bundle is valid.")

    col1, col2, col3 = st.columns(3)
    col1.metric("Configured metrics", config.metrics_count)
    col2.metric("Scoring profiles", config.profile_count)
    col3.metric("Default profile", config.default_profile or "N/A")

    if config.validation.messages:
        with st.expander("Validation details", expanded=False):
            for message in config.validation.messages:
                st.write(f"- {message}")

    if config.profiles:
        profile_df = pd.DataFrame(
            [
                {
                    "profile": item.name,
                    "metric_count": item.metric_count,
                    "year_strategy": item.year_strategy,
                    "missing_data_policy": item.missing_data_policy,
                    "description": item.description,
                }
                for item in config.profiles
            ]
        )
        st.write("**Available scoring profiles**")
        st.dataframe(
            profile_df,
            use_container_width=True,
            hide_index=True,
        )


def _render_error(error: AppError, *, debug: bool) -> None:
    st.error(f"{error.title}: {error.user_message}")

    if debug and error.technical_detail:
        with st.expander("Technical detail", expanded=False):
            st.code(error.technical_detail)
