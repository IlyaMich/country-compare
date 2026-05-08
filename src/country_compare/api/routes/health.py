from __future__ import annotations

from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Request, status
from fastapi.responses import JSONResponse

from country_compare import __version__
from country_compare.api.dependencies import get_app_facade
from country_compare.api.schemas.health import (
    HealthResponse,
    ReadyConfigStatus,
    ReadyDatasetStatus,
    ReadyResponse,
)
from country_compare.services.facade import AppFacade
from country_compare.services.models import OverviewStatus

router = APIRouter(tags=["operations"])


@router.get("/health", response_model=HealthResponse)
def health(request: Request) -> HealthResponse:
    """Return process-level liveness only."""

    api_settings = getattr(request.app.state, "api_settings", None)
    api_version = str(getattr(api_settings, "api_version", "0.2.0"))
    return HealthResponse(version=__version__, api_version=api_version)


@router.get(
    "/ready",
    response_model=ReadyResponse,
    responses={status.HTTP_503_SERVICE_UNAVAILABLE: {"model": ReadyResponse}},
)
def ready(
    facade: Annotated[AppFacade, Depends(get_app_facade)],
) -> ReadyResponse | JSONResponse:
    """Return strict traffic-readiness status."""

    overview = facade.get_overview_status(validate_config_against_dataset=True)
    payload = _build_ready_response(overview)

    if payload.status == "ready":
        return payload

    return JSONResponse(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        content=payload.model_dump(),
    )


def _build_ready_response(overview: OverviewStatus) -> ReadyResponse:
    dataset_exists = bool(overview.dataset.exists)
    dataset_schema_valid = overview.dataset.schema_valid is not False
    manifest_valid = overview.dataset.manifest_valid is True
    config_valid = bool(dataset_exists and overview.config.validation.valid)
    is_ready = (
        dataset_exists and dataset_schema_valid and manifest_valid and config_valid
    )

    ready_status: Literal["ready", "not_ready"] = "ready" if is_ready else "not_ready"

    config_messages = _validation_messages(overview)
    dataset_issue_messages = [
        str(message) for message in overview.dataset.schema_issues if str(message)
    ]

    return ReadyResponse(
        status=ready_status,
        dataset=ReadyDatasetStatus(
            exists=dataset_exists,
            backend=overview.dataset.backend,
            dataset_path=overview.dataset.dataset_path,
            row_count=overview.dataset.row_count,
            country_count=overview.dataset.country_count,
            metric_count=overview.dataset.metric_count,
            year_min=overview.dataset.year_min,
            year_max=overview.dataset.year_max,
            dataset_versions=list(overview.dataset.dataset_versions),
            dataset_checksum=overview.dataset.dataset_checksum,
            dataset_size_bytes=overview.dataset.dataset_size_bytes,
            dataset_modified_at=overview.dataset.dataset_modified_at,
            manifest_path=overview.dataset.manifest_path,
            manifest_exists=overview.dataset.manifest_exists,
            manifest_valid=overview.dataset.manifest_valid,
            manifest_issue_count=overview.dataset.manifest_issue_count,
            manifest_issues=list(overview.dataset.manifest_issues),
            manifest_dataset_version=overview.dataset.manifest_dataset_version,
            manifest_created_at=overview.dataset.manifest_created_at,
            manifest_schema_version=overview.dataset.manifest_schema_version,
            schema_valid=overview.dataset.schema_valid,
            schema_issue_count=overview.dataset.schema_issue_count,
            schema_issues=dataset_issue_messages,
            error=(
                overview.dataset.error.user_message
                if overview.dataset.error is not None
                else None
            ),
        ),
        config=ReadyConfigStatus(
            valid=config_valid,
            validated_against_dataset=True,
            metrics_count=overview.config.metrics_count,
            profile_count=overview.config.profile_count,
            messages=config_messages,
            error=(
                overview.config.error.user_message
                if overview.config.error is not None
                else None
            ),
        ),
        warnings=_build_warnings(overview),
    )


def _build_warnings(overview: OverviewStatus) -> list[str]:
    warnings = [str(warning) for warning in overview.warnings if str(warning)]

    if not overview.config.validation.valid:
        warnings.extend(_validation_messages(overview))

    if overview.dataset.schema_valid is False:
        warnings.extend(
            str(issue) for issue in overview.dataset.schema_issues if str(issue)
        )

    if overview.dataset.manifest_valid is not True:
        warnings.extend(
            str(issue) for issue in overview.dataset.manifest_issues if str(issue)
        )
        if overview.dataset.exists and not overview.dataset.manifest_exists:
            warnings.append("Dataset manifest is missing.")

    if not overview.dataset.exists and not warnings:
        warnings.append("No dataset is currently available.")

    return _deduplicate(warnings)


def _validation_messages(overview: OverviewStatus) -> list[str]:
    messages = [
        str(message) for message in overview.config.validation.messages if str(message)
    ]
    if overview.config.validation.error is not None:
        messages.append(overview.config.validation.error.user_message)
    return _deduplicate(messages)


def _deduplicate(values: list[str]) -> list[str]:
    unique_values: list[str] = []
    for value in values:
        if value not in unique_values:
            unique_values.append(value)

    return unique_values
