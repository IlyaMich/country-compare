from country_compare.ui.navigation import (
    AVAILABLE_PAGES,
    COMPARE_PAGE,
    CONFIG_EDITOR_PAGE,
    DEFAULT_PAGE,
    OVERVIEW_PAGE,
    PREDICTION_PAGE,
    available_pages_for_runtime,
    page_index,
)


def test_local_runtime_exposes_all_pages() -> None:
    pages = available_pages_for_runtime(config_editing=True)

    assert pages == AVAILABLE_PAGES
    assert CONFIG_EDITOR_PAGE in pages


def test_http_runtime_hides_config_editor() -> None:
    pages = available_pages_for_runtime(config_editing=False)

    assert pages == (
        OVERVIEW_PAGE,
        COMPARE_PAGE,
        PREDICTION_PAGE,
    )
    assert CONFIG_EDITOR_PAGE not in pages


def test_page_index_uses_runtime_page_collection() -> None:
    pages = available_pages_for_runtime(config_editing=False)

    assert (
        page_index(
            PREDICTION_PAGE,
            available_pages=pages,
        )
        == 2
    )


def test_page_index_falls_back_when_selected_page_is_unavailable() -> None:
    pages = available_pages_for_runtime(config_editing=False)

    index = page_index(
        CONFIG_EDITOR_PAGE,
        available_pages=pages,
    )

    assert pages[index] == DEFAULT_PAGE
