from __future__ import annotations

import streamlit as st

from country_compare.ui import state
from country_compare.ui.bootstrap import bootstrap_app
from country_compare.ui.views.overview import render_page as render_overview_page
from country_compare.ui.views.compare import render_compare_view


AVAILABLE_PAGES = ("Overview", "Compare", "Config Editor (coming soon)")

# VIEWS = {
#     "Overview": lambda facade, debug: render_overview_page(facade, debug=debug),
#     "Compare": lambda facade, debug: render_compare_view(),
# }

def main() -> None:
    st.set_page_config(
        page_title="Country Comparison",
        page_icon="🌍",
        layout="wide",
    )

    context, facade = bootstrap_app()
    
    views = {
        "Overview": lambda: render_overview_page(facade, debug=state.snapshot().debug_mode),
        "Compare": lambda: render_compare_view(context),
    }

    with st.sidebar:
        st.title("Country Compare")
        selected_page = st.radio("Page", AVAILABLE_PAGES, index=0)
        state.set_selected_page(selected_page)

        debug_mode = st.checkbox("Debug mode", value=state.snapshot().debug_mode)
        state.set_debug_mode(debug_mode)

        st.caption(f"Backend: {context.store_backend}")
        st.caption(f"Metrics config: {context.metrics_config_path}")
        st.caption(f"Scoring config: {context.scoring_config_path}")

    current_state = state.snapshot()
    view = views.get(current_state.selected_page)

    if view is not None:
        view()
    else:
        st.title(current_state.selected_page)
        st.info("This page is reserved for a later UI phase.")


if __name__ == "__main__":
    main()
