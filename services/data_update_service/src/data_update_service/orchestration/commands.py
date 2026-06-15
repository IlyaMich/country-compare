from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal, Self, cast, get_args
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

RefreshMode = Literal["full_refresh", "source_only", "validate_only"]
AcquisitionMode = Literal["local", "remote", "auto"]
CommandType = Literal["refresh_source"]
PromotionChannel = Literal["staging", "prod"]


def _normalize_portable_path(value: Any) -> str:
    """Normalize command paths for transport between Windows hosts and Linux containers.

    Kafka commands are JSON payloads, so paths should be serialized in a portable
    POSIX-like form. Without this, a command published from Windows may contain
    backslashes, and the Linux worker will treat them as literal filename
    characters.
    """
    normalized = str(value).strip().replace("\\", "/")
    if not normalized:
        raise ValueError("must not be empty")
    return normalized


def _coerce_acquisition_mode(value: Any) -> AcquisitionMode:
    normalized = str(value).strip().lower()
    if normalized not in get_args(AcquisitionMode):
        allowed = ", ".join(get_args(AcquisitionMode))
        raise ValueError(f"acquisition_mode must be one of: {allowed}")
    return cast(AcquisitionMode, normalized)


class RefreshCommand(BaseModel):
    """Command that describes one source refresh request.

    This schema is intentionally transport-neutral. The CLI creates it directly,
    and Kafka/private API adapters should pass the same model into
    `run_refresh_job()`.
    """

    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    schema_version: str = "1.0"
    command_id: str = Field(min_length=1)
    job_id: str = Field(min_length=1)
    idempotency_key: str = Field(min_length=1)
    command_type: CommandType = "refresh_source"
    source_family: str = Field(min_length=1)
    manifest_path: str = Field(min_length=1)
    mode: RefreshMode = "full_refresh"
    acquisition_mode: AcquisitionMode = "local"
    dry_run: bool = False
    publish: bool = True
    promote: bool = False
    promotion_channel: PromotionChannel | None = None
    requested_by: str = Field(min_length=1)
    requested_at: datetime
    correlation_id: str = Field(min_length=1)
    attempt: int = Field(default=1, ge=1)
    max_attempts: int = Field(default=3, ge=1)

    @field_validator("manifest_path", mode="before")
    @classmethod
    def _normalize_manifest_path(cls, value: Any) -> str:
        return _normalize_portable_path(value)

    @field_validator("acquisition_mode", mode="before")
    @classmethod
    def _normalize_acquisition_mode(cls, value: Any) -> AcquisitionMode:
        return _coerce_acquisition_mode(value)

    @field_validator(
        "command_id",
        "job_id",
        "idempotency_key",
        "source_family",
        "requested_by",
        "correlation_id",
    )
    @classmethod
    def _strip_required_text(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("must not be empty")
        return stripped

    @field_validator("source_family")
    @classmethod
    def _normalize_source_family(cls, value: str) -> str:
        return value.strip().lower()

    @field_validator("requested_at")
    @classmethod
    def _ensure_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value

    @model_validator(mode="after")
    def _validate_attempt_and_promotion(self) -> Self:
        if self.attempt > self.max_attempts:
            raise ValueError("attempt must be less than or equal to max_attempts")
        if self.promote and self.promotion_channel is None:
            raise ValueError("promotion_channel is required when promote=true")
        return self

    @property
    def manifest(self) -> Path:
        return Path(self.manifest_path)

    @classmethod
    def create(
        cls,
        *,
        source_family: str,
        manifest_path: str | Path,
        mode: RefreshMode = "full_refresh",
        acquisition_mode: AcquisitionMode = "local",
        dry_run: bool = False,
        publish: bool = True,
        promote: bool = False,
        promotion_channel: PromotionChannel | None = None,
        requested_by: str = "cli",
        requested_at: datetime | None = None,
        attempt: int = 1,
        max_attempts: int = 3,
        command_id: str | None = None,
        job_id: str | None = None,
        idempotency_key: str | None = None,
        correlation_id: str | None = None,
    ) -> RefreshCommand:
        normalized_source = source_family.strip().lower()
        normalized_manifest_path = _normalize_portable_path(manifest_path)
        normalized_acquisition_mode = _coerce_acquisition_mode(acquisition_mode)
        now = requested_at or datetime.now(UTC)
        timestamp = now.strftime("%Y%m%dT%H%M%SZ")
        command_suffix = uuid4().hex[:12]

        if normalized_acquisition_mode == "local":
            default_idempotency_key = (
                f"{normalized_source}:{mode}:{now.date().isoformat()}:{command_suffix}"
            )
        else:
            default_idempotency_key = (
                f"{normalized_source}:{mode}:{normalized_acquisition_mode}:"
                f"{now.date().isoformat()}:{command_suffix}"
            )

        return cls(
            command_id=command_id or f"cmd_{timestamp}_{command_suffix}",
            job_id=job_id or f"job_{timestamp}_{normalized_source}_{command_suffix}",
            idempotency_key=idempotency_key or default_idempotency_key,
            source_family=normalized_source,
            manifest_path=normalized_manifest_path,
            mode=mode,
            acquisition_mode=normalized_acquisition_mode,
            dry_run=dry_run,
            publish=publish,
            promote=promote,
            promotion_channel=promotion_channel,
            requested_by=requested_by,
            requested_at=now,
            correlation_id=correlation_id or f"corr_{command_suffix}",
            attempt=attempt,
            max_attempts=max_attempts,
        )
