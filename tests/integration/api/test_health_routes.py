from __future__ import annotations

from fastapi.testclient import TestClient

from country_compare import __version__
from country_compare.api.dependencies import get_app_facade
from country_compare.api.main import create_app
from country_compare.api.settings import ApiSettings
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
        "api_version": __version__,
    }


def test_health_returns_configured_api_version() -> None:
    app = create_app(settings=ApiSettings(api_version="2026.05-beta"))

    with TestClient(app) as client:
        response = client.get("/health")

    assert response.status_code == 200
    assert response.json()["api_version"] == "2026.05-beta"


def test_empty_cors_origins_does_not_allow_browser_origin() -> None:
    app = create_app(settings=ApiSettings(cors_origins=()))

    with TestClient(app) as client:
        response = client.get(
            "/health",
            headers={"Origin": "https://app.example.com"},
        )

    assert response.status_code == 200
    assert "access-control-allow-origin" not in response.headers


def test_ready_returns_200_when_dataset_exists_and_config_valid() -> None:
    overview = _overview(dataset_exists=True, config_valid=True)
    facade = FakeFacade(overview)
    client = _client_for(facade)

    response = client.get("/ready")

    assert response.status_code == 200
    assert response.json() == _ready_payload(
        status="ready",
        dataset_exists=True,
        config_valid=True,
        warnings=[],
    )
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
    assert response.json() == _ready_payload(
        status="not_ready",
        dataset_exists=False,
        config_valid=False,
        warnings=["No dataset is currently available."],
    )
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
    assert response.json() == _ready_payload(
        status="not_ready",
        dataset_exists=True,
        config_valid=False,
        config_messages=["Unknown metric_id: test_metric"],
        warnings=[
            "Configuration is not currently valid.",
            "Unknown metric_id: test_metric",
        ],
    )
    assert facade.validate_config_against_dataset_calls == [True]


def test_ready_returns_503_when_manifest_invalid() -> None:
    overview = _overview(
        dataset_exists=True,
        config_valid=True,
        manifest_valid=False,
        manifest_issues=("Dataset hash does not match manifest sha256.",),
    )
    facade = FakeFacade(overview)
    client = _client_for(facade)

    response = client.get("/ready")

    assert response.status_code == 503
    payload = response.json()
    assert payload["status"] == "not_ready"
    assert payload["dataset"]["manifest_valid"] is False
    assert payload["dataset"]["manifest_issues"] == [
        "Dataset hash does not match manifest sha256."
    ]
    assert payload["warnings"] == ["Dataset hash does not match manifest sha256."]


def _ready_payload(
    *,
    status: str,
    dataset_exists: bool,
    config_valid: bool,
    warnings: list[str],
    config_messages: list[str] | None = None,
    manifest_valid: bool | None = True,
) -> dict[str, object]:
    return {
        "status": status,
        "dataset": {
            "exists": dataset_exists,
            "backend": "parquet",
            "dataset_path": "data/processed/metrics.parquet",
            "row_count": 0,
            "country_count": 0,
            "metric_count": 0,
            "year_min": None,
            "year_max": None,
            "dataset_versions": [],
            "dataset_checksum": None,
            "dataset_size_bytes": None,
            "dataset_modified_at": None,
            "manifest_path": "data/processed/metrics_manifest.json",
            "manifest_exists": dataset_exists,
            "manifest_valid": manifest_valid if dataset_exists else False,
            "manifest_issue_count": 0,
            "manifest_issues": [],
            "manifest_dataset_version": None,
            "manifest_created_at": None,
            "manifest_schema_version": None,
            "schema_valid": None,
            "schema_issue_count": 0,
            "schema_issues": [],
            "error": None,
        },
        "config": {
            "valid": config_valid,
            "validated_against_dataset": True,
            "metrics_count": 0,
            "profile_count": 0,
            "messages": config_messages or [],
            "error": None,
        },
        "warnings": warnings,
    }


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
    manifest_valid: bool | None = True,
    manifest_issues: tuple[str, ...] = (),
) -> OverviewStatus:
    return OverviewStatus(
        dataset=DatasetSummary(
            exists=dataset_exists,
            backend="parquet",
            dataset_path="data/processed/metrics.parquet",
            manifest_path="data/processed/metrics_manifest.json",
            manifest_exists=dataset_exists,
            manifest_valid=manifest_valid if dataset_exists else False,
            manifest_issue_count=len(manifest_issues),
            manifest_issues=manifest_issues,
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
