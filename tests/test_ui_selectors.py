from country_compare.ui.components.selectors import get_prediction_method_options


def test_prediction_method_options_include_builtin_catalog_entries() -> None:
    methods = [
        {"method_id": "last_observed", "display_name": "Last observed", "description": "Carry forward."},
        {"method_id": "linear_trend", "display_name": "Linear trend", "description": "Trend extrapolation."},
        {"method_id": "moving_average", "display_name": "Moving average", "description": "Average recent years."},
    ]

    options, labels = get_prediction_method_options(methods)

    assert options == ["last_observed", "linear_trend", "moving_average"]
    assert labels["last_observed"].startswith("Last observed")
    assert labels["linear_trend"].startswith("Linear trend")
    assert labels["moving_average"].startswith("Moving average")
