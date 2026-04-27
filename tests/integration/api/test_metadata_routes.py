from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass

import pytest
from fastapi.testclient import TestClient

from country_compare.api.dependencies import get_app_facade
from country_compare.api.main import create_app
from country_compare.services.models import (
    CategorySummary,
    CountryOption,
    DatasetSummary,
    MetricOption,
    ProfileOption,
)


@dataclass(frozen=True)
class FakeScoringProfile:
    metrics: tuple[str, ...]


@dataclass(frozen=True)
class FakeScoringConfig:
    profiles: dict[str, FakeScoringProfile]


@dataclass(frozen=True)
class FakeConfigurationBundle:
    scoring: FakeScoringConfig


class FakeDatasetService:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def get_dataset_summary(self) -> DatasetSummary:
        self.calls.append("get_dataset_summary")
        return DatasetSummary(
            exists=True,
            backend="parquet",
            dataset_path="data/processed/metrics.parquet",
            row_count=12,
            country_count=2,
            metric_count=3,
            year_min=2020,
            year_max=2024,
            available_columns=("country_code", "country_name", "metric_id", "year"),
            categories=(
                CategorySummary(
                    name="economy",
                    row_count=8,
                    country_count=2,
                    metric_count=2,
                ),
            ),
        )

    def list_countries(self) -> tuple[CountryOption, ...]:
        self.calls.append("list_countries")
        return (
            CountryOption(code="ISR", name="Israel"),
            CountryOption(code="FRA", name="France"),
        )

    def list_metrics(self) -> tuple[MetricOption, ...]:
        self.calls.append("list_metrics")
        return (
            MetricOption(
                metric_id="gdp_per_capita",
                display_name="GDP per capita",
                category="economy",
                unit="USD",
            ),
            MetricOption(
                metric_id="life_expectancy",
                display_name="Life expectancy",
                category="health",
                unit="years",
            ),
        )

    def list_years(self) -> tuple[int, ...]:
        self.calls.append("list_years")
        return (2020, 2021, 2022, 2023, 2024)


class FakeConfigService:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def get_profile_summaries(self) -> tuple[ProfileOption, ...]:
        self.calls.append("get_profile_summaries")
        return (
            ProfileOption(
                name="economic_outlook",
                metric_count=2,
                description="Economic outlook profile",
                year_strategy="latest_per_metric",
                missing_data_policy="renormalize_weights",
            ),
        )

    def load_bundle(self, *, validate: bool = True) -> FakeConfigurationBundle:
        self.calls.append(f"load_bundle:{validate}")
        return FakeConfigurationBundle(
            scoring=FakeScoringConfig(
                profiles={
                    "economic_outlook": FakeScoringProfile(
                        metrics=("gdp_per_capita", "life_expectancy")
                    )
                }
            )
        )


class FakeFacade:
    def __init__(self) -> None:
        self.dataset = FakeDatasetService()
        self.config = FakeConfigService()


@pytest.fixture()
def client_and_facade() -> Iterator[tuple[TestClient, FakeFacade]]:
    fake_facade = FakeFacade()
    app = create_app()

    def override_get_app_facade() -> FakeFacade:
        return fake_facade

    app.dependency_overrides[get_app_facade] = override_get_app_facade

    with TestClient(app) as client:
        yield client, fake_facade

    app.dependency_overrides.clear()


def test_dataset_metadata_route(
    client_and_facade: tuple[TestClient, FakeFacade],
) -> None:
    client, fake_facade = client_and_facade

    response = client.get("/api/v1/metadata/dataset")

    assert response.status_code == 200
    assert response.json() == {
        "exists": True,
        "backend": "parquet",
        "dataset_path": "data/processed/metrics.parquet",
        "row_count": 12,
        "country_count": 2,
        "metric_count": 3,
        "year_min": 2020,
        "year_max": 2024,
        "available_columns": [
            "country_code",
            "country_name",
            "metric_id",
            "year",
        ],
        "categories": [
            {
                "name": "economy",
                "row_count": 8,
                "country_count": 2,
                "metric_count": 2,
            }
        ],
    }
    assert fake_facade.dataset.calls == ["get_dataset_summary"]


def test_country_metadata_route(
    client_and_facade: tuple[TestClient, FakeFacade],
) -> None:
    client, fake_facade = client_and_facade

    response = client.get("/api/v1/metadata/countries")

    assert response.status_code == 200
    assert response.json() == {
        "countries": [
            {"code": "ISR", "name": "Israel"},
            {"code": "FRA", "name": "France"},
        ]
    }
    assert fake_facade.dataset.calls == ["list_countries"]


def test_metric_metadata_route(
    client_and_facade: tuple[TestClient, FakeFacade],
) -> None:
    client, fake_facade = client_and_facade

    response = client.get("/api/v1/metadata/metrics")

    assert response.status_code == 200
    assert response.json() == {
        "metrics": [
            {
                "metric_id": "gdp_per_capita",
                "display_name": "GDP per capita",
                "category": "economy",
                "unit": "USD",
            },
            {
                "metric_id": "life_expectancy",
                "display_name": "Life expectancy",
                "category": "health",
                "unit": "years",
            },
        ]
    }
    assert fake_facade.dataset.calls == ["list_metrics"]


def test_year_metadata_route(
    client_and_facade: tuple[TestClient, FakeFacade],
) -> None:
    client, fake_facade = client_and_facade

    response = client.get("/api/v1/metadata/years")

    assert response.status_code == 200
    assert response.json() == {
        "years": [2020, 2021, 2022, 2023, 2024],
        "min_year": 2020,
        "max_year": 2024,
    }
    assert fake_facade.dataset.calls == ["list_years"]


def test_profile_metadata_route(
    client_and_facade: tuple[TestClient, FakeFacade],
) -> None:
    client, fake_facade = client_and_facade

    response = client.get("/api/v1/metadata/profiles")

    assert response.status_code == 200
    assert response.json() == {
        "profiles": [
            {
                "profile_name": "economic_outlook",
                "description": "Economic outlook profile",
                "metric_ids": ["gdp_per_capita", "life_expectancy"],
                "metric_count": 2,
                "year_strategy": "latest_per_metric",
                "missing_data_policy": "renormalize_weights",
            }
        ]
    }
    assert fake_facade.config.calls == [
        "get_profile_summaries",
        "load_bundle:True",
    ]


def test_metadata_routes_are_versioned(
    client_and_facade: tuple[TestClient, FakeFacade],
) -> None:
    client, _fake_facade = client_and_facade

    response = client.get("/metadata/dataset")

    assert response.status_code == 404
