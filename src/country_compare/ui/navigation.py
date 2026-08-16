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


def available_pages_for_runtime(
    *,
    config_editing: bool,
) -> tuple[str, ...]:
    """Return the pages available for the current UI runtime."""

    if config_editing:
        return AVAILABLE_PAGES

    return tuple(page for page in AVAILABLE_PAGES if page != CONFIG_EDITOR_PAGE)


def page_index(
    selected_page: str,
    *,
    available_pages: tuple[str, ...] = AVAILABLE_PAGES,
) -> int:
    """Return the sidebar radio index for a selected page.

    Falls back safely when state/config references an unavailable page.
    """

    if selected_page in available_pages:
        return available_pages.index(selected_page)

    if DEFAULT_PAGE in available_pages:
        return available_pages.index(DEFAULT_PAGE)

    return 0
