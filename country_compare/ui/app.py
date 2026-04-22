from __future__ import annotations

import streamlit as st

from country_compare.ui import query_state, state
from country_compare.ui.bootstrap import bootstrap_app
from country_compare.ui.views.compare import render_compare_view
from country_compare.ui.views.config_editor import render_config_editor_view
from country_compare.ui.views.overview import render_page as render_overview_page


AVAILABLE_PAGES = ("Overview", "Compare", "Config Editor")


def _page_index(selected_page: str) -> int:
    try:
        return AVAILABLE_PAGES.index(selected_page)
    except ValueError:
        return 0


def main() -> None:
    st.set_page_config(
        page_title="Country Comparison",
        page_icon="🌍",
        layout="wide",
    )

    context, facade = bootstrap_app()
    query_state.apply_query_params_once()

    views = {
        "Overview": lambda: render_overview_page(facade, debug=state.snapshot().debug_mode),
        "Compare": lambda: render_compare_view(context),
        "Config Editor": lambda: render_config_editor_view(context),
    }

    current_snapshot = state.snapshot()

    with st.sidebar:
        st.title("Country Compare")
        selected_page = st.radio(
            "Page",
            AVAILABLE_PAGES,
            index=_page_index(current_snapshot.selected_page),
        )
        state.set_selected_page(selected_page)

        debug_mode = st.checkbox("Debug mode", value=current_snapshot.debug_mode)
        state.set_debug_mode(debug_mode)

        st.caption(f"Backend: {context.store_backend}")
        st.caption(f"Metrics config: {context.metrics_config_path}")
        st.caption(f"Scoring config: {context.scoring_config_path}")

    query_state.sync_query_params_from_state(
        selected_page=selected_page,
        selection_state=state.get_selection_state(),
    )

    current_state = state.snapshot()
    view = views.get(current_state.selected_page)

    if view is not None:
        view()
    else:
        st.title(current_state.selected_page)
        st.info("This page is reserved for a later UI phase.")


if __name__ == "__main__":
    main()
