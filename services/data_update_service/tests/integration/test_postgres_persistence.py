from __future__ import annotations

import os
from datetime import UTC, datetime
from uuid import uuid4

import pytest

from data_update_service.infrastructure.job_store import DuplicateCommandConflictError
from data_update_service.infrastructure.locks import SourceLockUnavailableError
from data_update_service.infrastructure.postgres import (
    PostgresAttemptStore,
    PostgresJobStore,
    PostgresSourceLockManager,
)
from data_update_service.orchestration.commands import RefreshCommand
from data_update_service.orchestration.results import RefreshResult

pytestmark = pytest.mark.integration

DATABASE_URL_ENV = "DATA_UPDATE_TEST_DATABASE_URL"


@pytest.fixture()
def database_url() -> str:
    value = os.getenv(DATABASE_URL_ENV)
    if not value:
        pytest.skip(f"{DATABASE_URL_ENV} is not set")

    _reset_tables(value)
    yield value
    _reset_tables(value)


def test_postgres_job_store_replays_terminal_result_after_new_store_instance(
    database_url: str,
) -> None:
    command = _command("replay")

    store = PostgresJobStore(database_url, initialize_schema=True)
    created = store.create_or_get_job(command)
    assert created.status == "accepted"

    store.mark_running(command.job_id)
    result = RefreshResult(
        job_id=command.job_id,
        command_id=command.command_id,
        source_family=command.source_family,
        status="dry_run_completed",
        row_count=10,
        country_count=2,
        metric_count=1,
        year_min=2020,
        year_max=2024,
    )
    store.complete_job(result)

    new_store = PostgresJobStore(database_url)
    replayed = new_store.get_job(command.job_id)
    replayed_result = new_store.result_for_job(command.job_id)

    assert replayed is not None
    assert replayed.is_terminal
    assert replayed.status == "dry_run_completed"
    assert replayed_result is not None
    assert replayed_result.status == "dry_run_completed"
    assert replayed_result.row_count == 10


def test_postgres_job_store_reuses_duplicate_idempotent_command(
    database_url: str,
) -> None:
    command = _command("duplicate")

    store = PostgresJobStore(database_url, initialize_schema=True)

    first = store.create_or_get_job(command)
    second = store.create_or_get_job(command)

    assert second.job_id == first.job_id
    assert second.command_id == first.command_id
    assert second.idempotency_key == first.idempotency_key


def test_postgres_job_store_rejects_conflicting_duplicate_command(
    database_url: str,
) -> None:
    command = _command("conflict")

    store = PostgresJobStore(database_url, initialize_schema=True)
    store.create_or_get_job(command)

    conflicting = command.model_copy(
        update={"manifest_path": "config/source_manifests/other.yaml"}
    )

    with pytest.raises(DuplicateCommandConflictError):
        store.create_or_get_job(conflicting)


def test_postgres_source_lock_manager_blocks_concurrent_source_lock(
    database_url: str,
) -> None:
    first = PostgresSourceLockManager(
        database_url,
        ttl_seconds=60,
        initialize_schema=True,
    )
    second = PostgresSourceLockManager(
        database_url,
        ttl_seconds=60,
        initialize_schema=True,
    )

    with first.acquire("world_bank", "job_first"):
        with pytest.raises(SourceLockUnavailableError):
            with second.acquire("world_bank", "job_second"):
                pass

    assert second.current_lock("world_bank") is None


def _command(suffix: str) -> RefreshCommand:
    unique = f"{suffix}_{uuid4().hex[:8]}"
    return RefreshCommand.create(
        source_family="world_bank",
        manifest_path="config/source_manifests/world_bank_real_data.yaml",
        mode="full_refresh",
        acquisition_mode="remote",
        dry_run=True,
        publish=False,
        promote=False,
        promotion_channel="staging",
        requested_by="pytest",
        requested_at=datetime(2026, 1, 1, tzinfo=UTC),
        command_id=f"cmd_{unique}",
        job_id=f"job_{unique}",
        idempotency_key=f"idem_{unique}",
        correlation_id=f"corr_{unique}",
    )


def _reset_tables(database_url: str) -> None:
    try:
        import psycopg
    except ModuleNotFoundError:
        pytest.skip("psycopg is required for Postgres integration tests")

    with psycopg.connect(database_url, connect_timeout=5) as connection:
        connection.autocommit = True
        with connection.cursor() as cursor:
            cursor.execute("DROP TABLE IF EXISTS data_refresh_attempts")
            cursor.execute("DROP TABLE IF EXISTS source_locks")
            cursor.execute("DROP TABLE IF EXISTS data_refresh_jobs")


def test_postgres_attempt_store_records_attempt_lifecycle(database_url: str) -> None:
    command = _command("attempt")

    job_store = PostgresJobStore(database_url, initialize_schema=True)
    attempt_store = PostgresAttemptStore(database_url, initialize_schema=True)

    job_store.create_or_get_job(command)

    started = attempt_store.start_attempt(command, worker_id="pytest-worker")
    assert started.job_id == command.job_id
    assert started.command_id == command.command_id
    assert started.attempt_number == command.attempt
    assert started.status == "running"
    assert started.finished_at is None
    assert started.worker_id == "pytest-worker"

    finished = attempt_store.finish_attempt(
        started.attempt_id,
        status="failed_retryable",
        error_code="source_acquisition_retryable",
        error_message="temporary upstream outage",
    )

    assert finished.status == "failed_retryable"
    assert finished.finished_at is not None
    assert finished.error_code == "source_acquisition_retryable"
    assert finished.error_message == "temporary upstream outage"

    attempts = attempt_store.list_attempts(command.job_id)

    assert [attempt.attempt_id for attempt in attempts] == [started.attempt_id]
    assert attempts[0].status == "failed_retryable"


def test_postgres_job_store_advances_attempt_for_non_terminal_retry_command(
    database_url: str,
) -> None:
    command = _command("retry_attempt")

    store = PostgresJobStore(database_url, initialize_schema=True)

    created = store.create_or_get_job(command)
    assert created.attempt == 1

    store.update_status(command.job_id, "retry_scheduled")

    retry_command = command.model_copy(update={"attempt": 2})
    loaded = store.create_or_get_job(retry_command)

    assert loaded.job_id == command.job_id
    assert loaded.command_id == command.command_id
    assert loaded.idempotency_key == command.idempotency_key
    assert loaded.status == "retry_scheduled"
    assert loaded.attempt == 2
    assert loaded.max_attempts == command.max_attempts
