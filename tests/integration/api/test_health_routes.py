from __future__ import annotations

from fastapi.testclient import TestClient

from country_compare import __version__
from country_compare.api.dependencies import get_app_facade
from country_compare.api.main import create_app
from country_compare.services.models import (
    ConfigStatus,
    DatasetSummary,
    OverviewStatus,
    ValidationReport,
)


class FakeFacade:
    def __init__(self, overview: OverviewStatus) -> None:
        self.overview = overview
        self.validate_config_against_dataset_calls: list[bool] = []

    def get_overview_status(
        self, *, validate_config_against_dataset: bool = False
    ) -> OverviewStatus:
        self.validate_config_against_dataset_calls.append(
            validate_config_against_dataset
        )
        return self.overview


def test_health_returns_process_liveness_without_facade() -> None:
    app = create_app()

    def fail_if_called() -> None:
        raise AssertionError("/health must not resolve the application facade")

    app.dependency_overrides[get_app_facade] = fail_if_called

    with TestClient(app) as client:
        response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "service": "country-compare-api",
        "version": __version__,
    }


def test_ready_returns_200_when_dataset_exists_and_config_valid() -> None:
    overview = _overview(dataset_exists=True, config_valid=True)
    facade = FakeFacade(overview)
    client = _client_for(facade)

    response = client.get("/ready")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ready",
        "dataset": {"exists": True},
        "config": {"valid": True, "validated_against_dataset": True},
        "warnings": [],
    }
    assert facade.validate_config_against_dataset_calls == [True]


def test_ready_returns_503_when_dataset_missing() -> None:
    overview = _overview(
        dataset_exists=False,
        config_valid=True,
        warnings=("No dataset is currently available.",),
    )
    facade = FakeFacade(overview)
    client = _client_for(facade)

    response = client.get("/ready")

    assert response.status_code == 503
    assert response.json() == {
        "status": "not_ready",
        "dataset": {"exists": False},
        "config": {"valid": False, "validated_against_dataset": True},
        "warnings": ["No dataset is currently available."],
    }
    assert facade.validate_config_against_dataset_calls == [True]


def test_ready_returns_503_when_config_invalid() -> None:
    overview = _overview(
        dataset_exists=True,
        config_valid=False,
        warnings=("Configuration is not currently valid.",),
        validation_messages=("Unknown metric_id: test_metric",),
    )
    facade = FakeFacade(overview)
    client = _client_for(facade)

    response = client.get("/ready")

    assert response.status_code == 503
    assert response.json() == {
        "status": "not_ready",
        "dataset": {"exists": True},
        "config": {"valid": False, "validated_against_dataset": True},
        "warnings": [
            "Configuration is not currently valid.",
            "Unknown metric_id: test_metric",
        ],
    }
    assert facade.validate_config_against_dataset_calls == [True]


def _client_for(facade: FakeFacade) -> TestClient:
    app = create_app()
    app.dependency_overrides[get_app_facade] = lambda: facade
    return TestClient(app)


def _overview(
    *,
    dataset_exists: bool,
    config_valid: bool,
    warnings: tuple[str, ...] = (),
    validation_messages: tuple[str, ...] = (),
) -> OverviewStatus:
    return OverviewStatus(
        dataset=DatasetSummary(
            exists=dataset_exists,
            backend="parquet",
            dataset_path="data/processed/metrics.parquet",
        ),
        config=ConfigStatus(
            metrics_config_path="config/metrics.yaml",
            scoring_config_path="config/scoring_profiles.yaml",
            metrics_config_exists=True,
            scoring_config_exists=True,
            validation=ValidationReport(
                valid=config_valid,
                messages=validation_messages,
            ),
        ),
        warnings=warnings,
    )
