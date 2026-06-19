from __future__ import annotations

from datetime import UTC, datetime

from data_update_service.infrastructure.dataset_registry import (
    DatasetChannelRecord,
    DatasetVersionRecord,
)
from data_update_service.orchestration.commands import RefreshCommand
from data_update_service.orchestration.dataset_events import (
    InMemoryDatasetEventPublisher,
    make_dataset_promotion_event,
    make_dataset_version_event,
)


def _command() -> RefreshCommand:
    return RefreshCommand.create(
        source_family="world_bank",
        manifest_path="config/source_manifests/world_bank_real_data.yaml",
        mode="full_refresh",
        acquisition_mode="local",
        dry_run=False,
        publish=True,
        promote=True,
        promotion_channel="staging",
        requested_by="test",
    )


def test_make_dataset_version_event_from_registry_record() -> None:
    command = _command()
    created_at = datetime.now(tz=UTC)
    record = DatasetVersionRecord(
        dataset_version="world_bank_2026-06-19T08-38-21Z_15effb6",
        source_family="world_bank",
        artifact_uri="file:///tmp/artifacts/world_bank/versions/v1",
        parquet_sha256="a" * 64,
        validation_report_uri="file:///tmp/validation_report.json",
        diff_report_uri="file:///tmp/diff_report.json",
        row_count=10,
        country_count=2,
        metric_count=3,
        year_min=2000,
        year_max=2025,
        validation_status="passed",
        created_by_job_id=command.job_id,
        created_at=created_at,
        manifest_sha256="b" * 64,
        catalog_sha256="c" * 64,
    )

    event = make_dataset_version_event(command=command, record=record)

    assert event.job_id == command.job_id
    assert event.dataset_version == record.dataset_version
    assert event.source_family == "world_bank"
    assert event.validation_status == "passed"
    assert event.row_count == 10
    assert event.created_at == created_at


def test_make_dataset_promotion_event_from_channel_record() -> None:
    promoted_at = datetime.now(tz=UTC)
    record = DatasetChannelRecord(
        channel="staging",
        source_family="world_bank",
        dataset_version="world_bank_2026-06-19T08-38-21Z_15effb6",
        artifact_uri="file:///tmp/artifacts/world_bank/versions/v1",
        parquet_sha256="a" * 64,
        promoted_by="test",
        promoted_at=promoted_at,
    )

    event = make_dataset_promotion_event(
        record=record,
        previous_dataset_version="world_bank_previous",
    )

    assert event.channel == "staging"
    assert event.dataset_version == record.dataset_version
    assert event.previous_dataset_version == "world_bank_previous"
    assert event.promoted_by == "test"
    assert event.promoted_at == promoted_at


def test_in_memory_dataset_event_publisher_records_events() -> None:
    publisher = InMemoryDatasetEventPublisher()
    command = _command()
    version_record = DatasetVersionRecord(
        dataset_version="world_bank_v1",
        source_family="world_bank",
        artifact_uri="file:///tmp/artifacts/world_bank/versions/v1",
        parquet_sha256="a" * 64,
        validation_report_uri=None,
        diff_report_uri=None,
        row_count=1,
        country_count=1,
        metric_count=1,
        year_min=2020,
        year_max=2020,
        validation_status="passed",
        created_by_job_id=command.job_id,
        created_at=datetime.now(tz=UTC),
        manifest_sha256="b" * 64,
        catalog_sha256="c" * 64,
    )

    event = make_dataset_version_event(command=command, record=version_record)
    publisher.publish_dataset_version(event)

    assert publisher.version_events == [event]
    assert publisher.promotion_events == []
