from __future__ import annotations

from dataclasses import dataclass

from country_compare.clients.local import LocalCountryCompareClient
from country_compare.services.models import CountryOption, MetricOption, ProfileOption


@dataclass
class _FakeDatasetService:
    def get_dataset_summary(self):
        return {"exists": True}

    def get_country_catalog(self):
        return (CountryOption(code="ISR", name="Israel"),)

    def get_metric_catalog(self):
        return (MetricOption(metric_id="gdp", display_name="GDP"),)

    def list_years(self):
        return (2020, 2021)


@dataclass
class _FakeConfigService:
    def get_profile_summaries(self):
        return (ProfileOption(name="default", metric_count=1),)


@dataclass
class _FakePredictionService:
    def list_prediction_methods(self):
        return [{"method_id": "linear_trend", "display_name": "Linear trend"}]


def test_local_client_reads_catalogs_from_services(fake_app_context) -> None:
    client = LocalCountryCompareClient(
        context=fake_app_context,
        services={
            "dataset_service": _FakeDatasetService(),
            "config_service": _FakeConfigService(),
            "prediction_service": _FakePredictionService(),
        },
    )

    assert client.list_countries()[0].code == "ISR"
    assert client.list_metrics()[0].metric_id == "gdp"
    assert client.list_years() == [2020, 2021]
    assert client.list_profiles()[0].name == "default"
    assert client.list_prediction_methods()[0]["method_id"] == "linear_trend"
