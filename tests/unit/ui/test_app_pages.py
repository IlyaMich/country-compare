from country_compare.ui.app import AVAILABLE_PAGES


def test_prediction_page_is_registered() -> None:
    assert "Prediction" in AVAILABLE_PAGES
