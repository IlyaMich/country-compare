from __future__ import annotations

from typing import Annotated, Any, Literal, TypedDict

from fastapi import APIRouter, Depends, Request, status
from fastapi.responses import JSONResponse

from country_compare import __version__
from country_compare.api.dependencies import get_app_facade
from country_compare.api.schemas.health import (
    HealthResponse,
    LLMReadyResponse,
    ReadyConfigStatus,
    ReadyDatasetStatus,
    ReadyResponse,
)
from country_compare.prediction.llm.forecasters import (
    ENV_ENABLE_LLM_FORECAST,
    ENV_LLM_SERVICE_TOKEN,
    ENV_LLM_SERVICE_URL,
    load_llm_forecast_settings,
)
from country_compare.prediction.llm.remote_client import (
    RemoteLLMForecastClient,
    RemoteLLMForecastError,
)
from country_compare.services.facade import AppFacade
from country_compare.services.models import OverviewStatus

router = APIRouter(tags=["operations"])


@router.get("/health", response_model=HealthResponse)
def health(request: Request) -> HealthResponse:
    """Return process-level liveness only."""

    api_settings = getattr(request.app.state, "api_settings", None)
    api_version = str(getattr(api_settings, "api_version", __version__))
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


@router.get(
    "/ready/llm",
    response_model=LLMReadyResponse,
    responses={status.HTTP_503_SERVICE_UNAVAILABLE: {"model": LLMReadyResponse}},
)
def llm_ready() -> LLMReadyResponse | JSONResponse:
    """Return backend-to-LLM-service readiness without running a forecast."""

    payload = _build_llm_ready_response()
    if payload.status == "ready":
        return payload

    return JSONResponse(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        content=payload.model_dump(mode="json"),
    )


class _LLMReadyBasePayload(TypedDict):
    enabled: bool
    service_url_configured: bool
    service_token_configured: bool
    provider: str
    model: str


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


def _build_llm_ready_response() -> LLMReadyResponse:
    settings = load_llm_forecast_settings()
    base_payload: _LLMReadyBasePayload = {
        "enabled": settings.enabled,
        "service_url_configured": bool(settings.service_url),
        "service_token_configured": bool(settings.service_token),
        "provider": settings.provider,
        "model": settings.model,
    }

    config_warnings = _llm_config_warnings(
        enabled=settings.enabled,
        service_url=settings.service_url,
        service_token=settings.service_token,
    )
    if config_warnings:
        return LLMReadyResponse(
            status="not_ready",
            **base_payload,
            warnings=config_warnings,
        )

    client = RemoteLLMForecastClient(
        service_url=settings.service_url,
        service_token=settings.service_token,
        timeout_seconds=min(settings.service_timeout_seconds, 5.0),
        max_adjustment_pct=settings.max_adjustment_pct,
    )

    try:
        capabilities = client.capabilities()
    except RemoteLLMForecastError as exc:
        return LLMReadyResponse(
            status="not_ready",
            **base_payload,
            warnings=["Backend could not reach a ready LLM forecast service."],
            error=str(exc),
        )
    except Exception as exc:
        return LLMReadyResponse(
            status="not_ready",
            **base_payload,
            warnings=["Backend LLM readiness check failed unexpectedly."],
            error=f"{exc.__class__.__name__}: {exc}",
        )

    capability_warnings = _llm_capability_warnings(capabilities)
    return LLMReadyResponse(
        status="ready" if not capability_warnings else "not_ready",
        **base_payload,
        capabilities={str(key): value for key, value in capabilities.items()},
        warnings=capability_warnings,
    )


def _llm_config_warnings(
    *,
    enabled: bool,
    service_url: str,
    service_token: str,
) -> list[str]:
    warnings: list[str] = []

    if not enabled:
        warnings.append(
            f"llm_forecast is disabled; set {ENV_ENABLE_LLM_FORECAST}=true "
            "to enable it."
        )
    if not service_url:
        warnings.append(f"{ENV_LLM_SERVICE_URL} is not configured.")
    if not service_token:
        warnings.append(f"{ENV_LLM_SERVICE_TOKEN} is not configured.")

    return warnings


def _llm_capability_warnings(capabilities: dict[str, Any]) -> list[str]:
    warnings: list[str] = []

    if not bool(capabilities.get("supports_structured_output")):
        warnings.append("LLM service does not report structured output support.")
    if not bool(capabilities.get("supports_bounded_adjustment")):
        warnings.append("LLM service does not report bounded adjustment support.")

    max_series_per_request = _optional_int(capabilities.get("max_series_per_request"))
    if max_series_per_request is None or max_series_per_request < 1:
        warnings.append("LLM service max_series_per_request is invalid.")

    max_horizon_years = _optional_int(capabilities.get("max_horizon_years"))
    if max_horizon_years is None or max_horizon_years < 1:
        warnings.append("LLM service max_horizon_years is invalid.")

    return warnings


def _optional_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
