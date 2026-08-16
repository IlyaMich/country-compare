from country_compare.ui.navigation import (
    AVAILABLE_PAGES,
    PREDICTION_PAGE,
)


def test_prediction_page_is_registered() -> None:
    assert PREDICTION_PAGE in AVAILABLE_PAGES
