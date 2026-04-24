from country_compare.services.prediction_service import PredictionService
from country_compare.ui.bootstrap import build_app_context, get_ui_services, refresh_cached_services


def test_ui_services_include_prediction_service() -> None:
    refresh_cached_services()
    context = build_app_context(debug=False)
    services = get_ui_services(context)

    assert "prediction_service" in services
    assert isinstance(services["prediction_service"], PredictionService)
