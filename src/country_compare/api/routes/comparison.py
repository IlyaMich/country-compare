from __future__ import annotations

from typing import Annotated, Any, TypeAlias

from fastapi import APIRouter, Depends, Request, status
from fastapi.responses import JSONResponse

from country_compare.api.dependencies import get_app_facade
from country_compare.api.limits import enforce_country_limit, enforce_metric_limit
from country_compare.api.schemas.common import ResultEnvelope
from country_compare.api.schemas.comparison import (
    MultiMetricComparisonRequest,
    SingleMetricComparisonRequest,
    WeightedScoreComparisonRequest,
)
from country_compare.api.serialization import (
    DEFAULT_MAX_RECORDS,
    serialize_result_envelope,
)
from country_compare.services.facade import AppFacade
from country_compare.services.requests import (
    MultiMetricRequest,
    SingleMetricRequest,
    WeightedScoreRequest,
)

router = APIRouter()

FacadeDependency: TypeAlias = Annotated[AppFacade, Depends(get_app_facade)]

_ERROR_RESPONSES: dict[int | str, dict[str, Any]] = {
    status.HTTP_400_BAD_REQUEST: {"model": ResultEnvelope},
    status.HTTP_404_NOT_FOUND: {"model": ResultEnvelope},
    status.HTTP_409_CONFLICT: {"model": ResultEnvelope},
    status.HTTP_500_INTERNAL_SERVER_ERROR: {"model": ResultEnvelope},
}


@router.post(
    "/compare/single-metric",
    response_model=ResultEnvelope,
    responses=_ERROR_RESPONSES,
)
def compare_single_metric(
    body: SingleMetricComparisonRequest,
    request: Request,
    facade: FacadeDependency,
) -> ResultEnvelope | JSONResponse:
    """Run a read-only single-metric country comparison."""

    enforce_country_limit(request, body.country_codes)

    service_request = SingleMetricRequest(
        countries=body.country_codes,
        metric_id=body.metric_id,
        year_strategy=body.year_strategy,
        target_year=body.target_year,
        top_n=body.top_n,
    )
    _result, presentation = facade.compare_single_metric(service_request)
    return _presentation_response(
        presentation,
        request=request,
        mode="single_metric",
    )


@router.post(
    "/compare/multi-metric",
    response_model=ResultEnvelope,
    responses=_ERROR_RESPONSES,
)
def compare_multi_metric(
    body: MultiMetricComparisonRequest,
    request: Request,
    facade: FacadeDependency,
) -> ResultEnvelope | JSONResponse:
    """Run a read-only multi-metric country comparison."""

    enforce_country_limit(request, body.country_codes)
    enforce_metric_limit(request, body.metric_ids)

    service_request = MultiMetricRequest(
        countries=body.country_codes,
        metric_ids=body.metric_ids,
        year_strategy=body.year_strategy,
        target_year=body.target_year,
        top_n=body.top_n,
    )
    _result, presentation = facade.compare_multi_metric(service_request)
    return _presentation_response(
        presentation,
        request=request,
        mode="multi_metric",
    )


@router.post(
    "/score/profile",
    response_model=ResultEnvelope,
    responses=_ERROR_RESPONSES,
)
def compare_weighted_score(
    body: WeightedScoreComparisonRequest,
    request: Request,
    facade: FacadeDependency,
) -> ResultEnvelope | JSONResponse:
    """Run a read-only weighted scoring comparison for a configured profile."""

    enforce_country_limit(request, body.country_codes)

    service_request = WeightedScoreRequest(
        countries=body.country_codes,
        profile_name=body.profile_name,
        year_strategy=body.year_strategy,
        target_year=body.target_year,
        top_n=body.top_n,
    )
    _result, presentation = facade.compare_weighted_score(service_request)
    return _presentation_response(
        presentation,
        request=request,
        mode="weighted_score",
    )


def _presentation_response(
    presentation: Any,
    *,
    request: Request,
    mode: str,
) -> ResultEnvelope | JSONResponse:
    envelope = serialize_result_envelope(
        presentation,
        mode=mode,
        max_records=_max_records_from_request(request),
    )

    if envelope.ok:
        return envelope

    return JSONResponse(
        status_code=_status_for_envelope(envelope),
        content=envelope.model_dump(mode="json"),
    )


def _max_records_from_request(request: Request) -> int:
    api_settings = getattr(request.app.state, "api_settings", None)
    raw_max_records = getattr(api_settings, "max_records", DEFAULT_MAX_RECORDS)
    return int(raw_max_records)


def _status_for_envelope(envelope: ResultEnvelope) -> int:
    error = envelope.error
    if error is None:
        return status.HTTP_500_INTERNAL_SERVER_ERROR

    if error.code == "resource_not_found":
        return status.HTTP_404_NOT_FOUND
    if error.code in {
        "configuration_invalid",
        "config_invalid",
        "dataset_invalid",
        "state_invalid",
    }:
        return status.HTTP_409_CONFLICT
    if error.code in {
        "comparison_failed",
        "input_invalid",
        "input_limit_exceeded",
        "scoring_failed",
        "selection_invalid",
        "validation_failed",
    }:
        return status.HTTP_400_BAD_REQUEST

    return status.HTTP_500_INTERNAL_SERVER_ERROR
