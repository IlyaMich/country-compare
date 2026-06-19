from __future__ import annotations

from collections.abc import MutableSequence
from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING, Literal, Protocol
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

from data_update_service.orchestration.commands import PromotionChannel, RefreshCommand

if TYPE_CHECKING:
    from data_update_service.infrastructure.dataset_registry import (
        DatasetChannelRecord,
        DatasetVersionRecord,
    )


ValidationStatus = Literal["passed", "failed"]


class DatasetVersionEvent(BaseModel):
    """Event emitted after a dataset version is registered."""

    model_config = ConfigDict(extra="forbid")

    schema_version: str = "1.0"
    event_id: str = Field(min_length=1)
    job_id: str = Field(min_length=1)
    dataset_version: str = Field(min_length=1)
    source_family: str = Field(min_length=1)
    artifact_uri: str = Field(min_length=1)
    parquet_sha256: str = Field(min_length=1)
    manifest_sha256: str = ""
    catalog_sha256: str = ""
    validation_status: ValidationStatus
    row_count: int = Field(ge=0)
    country_count: int = Field(ge=0)
    metric_count: int = Field(ge=0)
    year_min: int | None = None
    year_max: int | None = None
    created_at: datetime


class DatasetPromotionEvent(BaseModel):
    """Event emitted after a dataset version is promoted to a channel."""

    model_config = ConfigDict(extra="forbid")

    schema_version: str = "1.0"
    event_id: str = Field(min_length=1)
    dataset_version: str = Field(min_length=1)
    channel: PromotionChannel
    previous_dataset_version: str | None = None
    promoted_by: str = Field(min_length=1)
    promoted_at: datetime


class DatasetEventPublisher(Protocol):
    def publish_dataset_version(self, event: DatasetVersionEvent) -> None:
        """Publish a dataset-version event."""

    def publish_dataset_promotion(self, event: DatasetPromotionEvent) -> None:
        """Publish a dataset-promotion event."""


class NoopDatasetEventPublisher:
    """Publisher used by CLI/local runs when no event bus is configured."""

    def publish_dataset_version(self, event: DatasetVersionEvent) -> None:
        return None

    def publish_dataset_promotion(self, event: DatasetPromotionEvent) -> None:
        return None


@dataclass(slots=True)
class InMemoryDatasetEventPublisher:
    """Deterministic publisher fake for unit tests."""

    version_events: MutableSequence[DatasetVersionEvent] = field(default_factory=list)
    promotion_events: MutableSequence[DatasetPromotionEvent] = field(
        default_factory=list
    )

    def publish_dataset_version(self, event: DatasetVersionEvent) -> None:
        self.version_events.append(event)

    def publish_dataset_promotion(self, event: DatasetPromotionEvent) -> None:
        self.promotion_events.append(event)


def make_dataset_version_event(
    *,
    command: RefreshCommand,
    record: DatasetVersionRecord,
) -> DatasetVersionEvent:
    return DatasetVersionEvent(
        event_id=f"evt_dataset_version_{uuid4().hex}",
        job_id=command.job_id,
        dataset_version=record.dataset_version,
        source_family=record.source_family,
        artifact_uri=record.artifact_uri,
        parquet_sha256=record.parquet_sha256,
        manifest_sha256=record.manifest_sha256,
        catalog_sha256=record.catalog_sha256,
        validation_status=record.validation_status,  # type: ignore[arg-type]
        row_count=record.row_count,
        country_count=record.country_count,
        metric_count=record.metric_count,
        year_min=record.year_min,
        year_max=record.year_max,
        created_at=record.created_at,
    )


def make_dataset_promotion_event(
    *,
    record: DatasetChannelRecord,
    previous_dataset_version: str | None,
) -> DatasetPromotionEvent:
    return DatasetPromotionEvent(
        event_id=f"evt_dataset_promotion_{uuid4().hex}",
        dataset_version=record.dataset_version,
        channel=record.channel,
        previous_dataset_version=previous_dataset_version,
        promoted_by=record.promoted_by,
        promoted_at=record.promoted_at,
    )
