from __future__ import annotations

from typing import Annotated, Literal

from fastapi import APIRouter, Depends, status
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
def health() -> HealthResponse:
    """Return process-level liveness only."""

    return HealthResponse(version=__version__)


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
    config_valid = bool(dataset_exists and overview.config.validation.valid)
    is_ready = dataset_exists and config_valid

    ready_status: Literal["ready", "not_ready"] = "ready" if is_ready else "not_ready"

    return ReadyResponse(
        status=ready_status,
        dataset=ReadyDatasetStatus(exists=dataset_exists),
        config=ReadyConfigStatus(
            valid=config_valid,
            validated_against_dataset=True,
        ),
        warnings=_build_warnings(overview),
    )


def _build_warnings(overview: OverviewStatus) -> list[str]:
    warnings = [str(warning) for warning in overview.warnings if str(warning)]

    validation_messages = (
        str(message) for message in overview.config.validation.messages if str(message)
    )
    if not overview.config.validation.valid:
        warnings.extend(validation_messages)

    if not overview.dataset.exists and not warnings:
        warnings.append("No dataset is currently available.")

    return _deduplicate(warnings)


def _deduplicate(values: list[str]) -> list[str]:
    unique_values: list[str] = []
    for value in values:
        if value not in unique_values:
            unique_values.append(value)

    return unique_values
