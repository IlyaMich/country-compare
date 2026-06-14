from __future__ import annotations

from datetime import UTC, datetime

import pytest

from data_update_service.infrastructure.job_store import (
    DuplicateCommandConflictError,
    InMemoryJobStore,
)
from data_update_service.orchestration.commands import RefreshCommand
from data_update_service.orchestration.results import RefreshResult


def _command() -> RefreshCommand:
    return RefreshCommand.create(
        source_family="world_bank",
        manifest_path="manifest.yaml",
        requested_at=datetime(2026, 6, 13, tzinfo=UTC),
        command_id="cmd-1",
        job_id="job-1",
        idempotency_key="world_bank:full_refresh:2026-06-13",
        correlation_id="corr-1",
    )


def test_in_memory_job_store_creates_and_gets_job() -> None:
    store = InMemoryJobStore()
    command = _command()

    record = store.create_or_get_job(command)

    assert record.job_id == "job-1"
    assert record.status == "accepted"
    assert store.get_job("job-1") == record


def test_in_memory_job_store_returns_existing_job_for_duplicate_command() -> None:
    store = InMemoryJobStore()
    command = _command()

    first = store.create_or_get_job(command)
    second = store.create_or_get_job(command)

    assert first == second


def test_in_memory_job_store_rejects_conflicting_duplicate_command_id() -> None:
    store = InMemoryJobStore()
    command = _command()
    store.create_or_get_job(command)
    conflicting = command.model_copy(update={"job_id": "job-2"})

    with pytest.raises(DuplicateCommandConflictError):
        store.create_or_get_job(conflicting)


def test_in_memory_job_store_records_status_history_and_result() -> None:
    store = InMemoryJobStore()
    command = _command()
    store.create_or_get_job(command)
    store.mark_running(command.job_id)
    store.update_status(command.job_id, "pipeline_completed")
    result = RefreshResult(
        job_id=command.job_id,
        command_id=command.command_id,
        source_family=command.source_family,
        status="dry_run_completed",
    )

    record = store.complete_job(result)

    assert record.is_terminal
    assert record.status == "dry_run_completed"
    assert record.result == result
    assert record.status_history == (
        "accepted",
        "running",
        "pipeline_completed",
        "dry_run_completed",
    )
    assert store.result_for_job(command.job_id) == result
