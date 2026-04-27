from __future__ import annotations

from typing import Final

from country_compare.settings.defaults import DEFAULT_UI_DEFAULT_PAGE

OVERVIEW_PAGE: Final[str] = "Overview"
COMPARE_PAGE: Final[str] = "Compare"
PREDICTION_PAGE: Final[str] = "Prediction"
CONFIG_EDITOR_PAGE: Final[str] = "Config Editor"

AVAILABLE_PAGES: Final[tuple[str, ...]] = (
    OVERVIEW_PAGE,
    COMPARE_PAGE,
    PREDICTION_PAGE,
    CONFIG_EDITOR_PAGE,
)
DEFAULT_PAGE: Final[str] = DEFAULT_UI_DEFAULT_PAGE


def page_index(selected_page: str) -> int:
    """Return the sidebar radio index for a selected page.

    Falls back safely when state/config references an unknown page.
    """
    if selected_page in AVAILABLE_PAGES:
        return AVAILABLE_PAGES.index(selected_page)

    if DEFAULT_PAGE in AVAILABLE_PAGES:
        return AVAILABLE_PAGES.index(DEFAULT_PAGE)

    return 0
