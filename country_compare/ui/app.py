from __future__ import annotations

import streamlit as st

from country_compare.settings import load_app_settings
from country_compare.ui import state
from country_compare.ui.bootstrap import bootstrap_app
from country_compare.ui.navigation import (
    AVAILABLE_PAGES,
    COMPARE_PAGE,
    CONFIG_EDITOR_PAGE,
    OVERVIEW_PAGE,
    PREDICTION_PAGE,
    page_index,
)
from country_compare.ui.text import (
    DEBUG_CHECKBOX_LABEL,
    PAGE_RADIO_LABEL,
    RESERVED_PAGE_INFO,
    SIDEBAR_TITLE,
    backend_caption,
    metrics_config_caption,
    scoring_config_caption,
)
from country_compare.ui.views.compare import render_compare_view
from country_compare.ui.views.config_editor import render_config_editor_view
from country_compare.ui.views.overview import render_page as render_overview_page
from country_compare.ui.views.prediction import render_prediction_view


def main() -> None:
    app_settings = load_app_settings()
    st.set_page_config(
        page_title=app_settings.ui.page_title,
        page_icon=app_settings.ui.page_icon,
        layout=app_settings.ui.layout,
    )

    context, facade = bootstrap_app(settings=app_settings)

    views = {
        OVERVIEW_PAGE: lambda: render_overview_page(
            facade, debug=state.snapshot().debug_mode
        ),
        COMPARE_PAGE: lambda: render_compare_view(context),
        PREDICTION_PAGE: lambda: render_prediction_view(context),
        CONFIG_EDITOR_PAGE: lambda: render_config_editor_view(context),
    }

    current_snapshot = state.snapshot()

    with st.sidebar:
        st.title(context.settings.ui.app_title if context.settings else SIDEBAR_TITLE)
        selected_page = st.radio(
            PAGE_RADIO_LABEL,
            AVAILABLE_PAGES,
            index=page_index(current_snapshot.selected_page),
        )
        state.set_selected_page(selected_page)

        debug_mode = st.checkbox(
            DEBUG_CHECKBOX_LABEL, value=current_snapshot.debug_mode
        )
        state.set_debug_mode(debug_mode)

        st.caption(backend_caption(context.store_backend))
        st.caption(metrics_config_caption(context.metrics_config_path))
        st.caption(scoring_config_caption(context.scoring_config_path))

    current_state = state.snapshot()
    view = views.get(current_state.selected_page)

    if view is not None:
        view()
    else:
        st.title(current_state.selected_page)
        st.info(RESERVED_PAGE_INFO)


if __name__ == "__main__":
    main()
