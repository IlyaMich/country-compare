from __future__ import annotations

from collections.abc import Mapping
from typing import Annotated, Any, TypeAlias

from fastapi import APIRouter, Depends

from country_compare.api.dependencies import get_app_facade
from country_compare.api.schemas.metadata import (
    CategorySummaryResponse,
    CountriesMetadataResponse,
    CountryOptionResponse,
    DatasetMetadataResponse,
    MetricOptionResponse,
    MetricsMetadataResponse,
    PredictionMethodResponse,
    PredictionMethodsMetadataResponse,
    ProfileOptionResponse,
    ProfilesMetadataResponse,
    YearsMetadataResponse,
)
from country_compare.services.facade import AppFacade
from country_compare.services.models import (
    CategorySummary,
    CountryOption,
    DatasetSummary,
    MetricOption,
    ProfileOption,
)

router = APIRouter()

FacadeDependency: TypeAlias = Annotated[AppFacade, Depends(get_app_facade)]


@router.get("/dataset", response_model=DatasetMetadataResponse)
def get_dataset_metadata(facade: FacadeDependency) -> DatasetMetadataResponse:
    """Return processed dataset metadata for UI selector/bootstrap flows."""

    return _to_dataset_response(facade.dataset.get_dataset_summary())


@router.get("/countries", response_model=CountriesMetadataResponse)
def get_country_metadata(facade: FacadeDependency) -> CountriesMetadataResponse:
    """Return available country options from the processed dataset."""

    countries = facade.dataset.list_countries()
    return CountriesMetadataResponse(
        countries=[_to_country_response(country) for country in countries]
    )


@router.get("/metrics", response_model=MetricsMetadataResponse)
def get_metric_metadata(facade: FacadeDependency) -> MetricsMetadataResponse:
    """Return available metric options from the processed dataset."""

    metrics = facade.dataset.list_metrics()
    return MetricsMetadataResponse(
        metrics=[_to_metric_response(metric) for metric in metrics]
    )


@router.get("/years", response_model=YearsMetadataResponse)
def get_year_metadata(facade: FacadeDependency) -> YearsMetadataResponse:
    """Return available dataset years and derived bounds."""

    years = list(facade.dataset.list_years())
    return YearsMetadataResponse(
        years=years,
        min_year=min(years) if years else None,
        max_year=max(years) if years else None,
    )


@router.get("/profiles", response_model=ProfilesMetadataResponse)
def get_profile_metadata(facade: FacadeDependency) -> ProfilesMetadataResponse:
    """Return scoring profile summaries from the configuration service."""

    profiles = facade.config.get_profile_summaries()
    metric_ids_by_profile = _profile_metric_ids_by_name(
        facade.config.load_bundle(validate=True)
    )
    return ProfilesMetadataResponse(
        profiles=[
            _to_profile_response(
                profile,
                metric_ids=metric_ids_by_profile.get(profile.name, []),
            )
            for profile in profiles
        ]
    )


@router.get("/prediction-methods", response_model=PredictionMethodsMetadataResponse)
def get_prediction_method_metadata(
    facade: FacadeDependency,
) -> PredictionMethodsMetadataResponse:
    """Return prediction method options from the backend runtime."""

    return PredictionMethodsMetadataResponse(
        methods=[
            _to_prediction_method_response(method)
            for method in facade.prediction.list_prediction_methods()
        ]
    )


def _to_dataset_response(summary: DatasetSummary) -> DatasetMetadataResponse:
    return DatasetMetadataResponse(
        exists=summary.exists,
        backend=summary.backend,
        dataset_path=summary.dataset_path,
        row_count=summary.row_count,
        country_count=summary.country_count,
        metric_count=summary.metric_count,
        year_min=summary.year_min,
        year_max=summary.year_max,
        available_columns=list(summary.available_columns),
        categories=[_to_category_response(category) for category in summary.categories],
        dataset_versions=list(summary.dataset_versions),
        dataset_checksum=summary.dataset_checksum,
        dataset_size_bytes=summary.dataset_size_bytes,
        dataset_modified_at=summary.dataset_modified_at,
        schema_valid=summary.schema_valid,
        schema_issue_count=summary.schema_issue_count,
        schema_issues=list(summary.schema_issues),
    )


def _to_category_response(category: CategorySummary) -> CategorySummaryResponse:
    return CategorySummaryResponse(
        name=category.name,
        row_count=category.row_count,
        country_count=category.country_count,
        metric_count=category.metric_count,
    )


def _to_country_response(country: CountryOption) -> CountryOptionResponse:
    return CountryOptionResponse(code=country.code, name=country.name)


def _to_metric_response(metric: MetricOption) -> MetricOptionResponse:
    return MetricOptionResponse(
        metric_id=metric.metric_id,
        display_name=metric.display_name,
        category=metric.category,
        unit=metric.unit,
    )


def _to_profile_response(
    profile: ProfileOption,
    *,
    metric_ids: list[str],
) -> ProfileOptionResponse:
    return ProfileOptionResponse(
        profile_name=profile.name,
        description=profile.description,
        metric_ids=metric_ids,
        metric_count=profile.metric_count,
        year_strategy=profile.year_strategy,
        missing_data_policy=profile.missing_data_policy,
    )


def _to_prediction_method_response(
    method: Mapping[str, Any],
) -> PredictionMethodResponse:
    return PredictionMethodResponse(
        method_id=str(method.get("method_id") or ""),
        display_name=str(method.get("display_name") or method.get("method_id") or ""),
        description=str(method.get("description") or ""),
        metadata=dict(method.get("metadata") or {}),
    )


def _profile_metric_ids_by_name(bundle: Any) -> dict[str, list[str]]:
    scoring = getattr(bundle, "scoring", None)
    profiles = getattr(scoring, "profiles", {})
    if not isinstance(profiles, Mapping):
        return {}

    metric_ids_by_profile: dict[str, list[str]] = {}
    for profile_name, profile in profiles.items():
        metric_ids = getattr(profile, "metrics", ())
        metric_ids_by_profile[str(profile_name)] = [
            str(metric_id) for metric_id in metric_ids
        ]
    return metric_ids_by_profile
