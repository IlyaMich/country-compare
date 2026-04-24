from __future__ import annotations

from country_compare.settings.defaults import DEFAULT_UI_DEFAULT_PAGE

OVERVIEW_PAGE = "Overview"
COMPARE_PAGE = "Compare"
PREDICTION_PAGE = "Prediction"
CONFIG_EDITOR_PAGE = "Config Editor"

AVAILABLE_PAGES = (
    OVERVIEW_PAGE,
    COMPARE_PAGE,
    PREDICTION_PAGE,
    CONFIG_EDITOR_PAGE,
)
DEFAULT_PAGE = DEFAULT_UI_DEFAULT_PAGE


def page_index(selected_page: str) -> int:
    try:
        return AVAILABLE_PAGES.index(selected_page)
    except ValueError:
        return (
            AVAILABLE_PAGES.index(DEFAULT_PAGE)
            if DEFAULT_PAGE in AVAILABLE_PAGES
            else 0
        )
