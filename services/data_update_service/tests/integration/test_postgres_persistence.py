from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

import pandas as pd
import pytest

from data_update_service.infrastructure.job_store import DuplicateCommandConflictError
from data_update_service.infrastructure.locks import SourceLockUnavailableError
from data_update_service.infrastructure.postgres import (
    PostgresAttemptStore,
    PostgresDatasetRegistry,
    PostgresJobStore,
    PostgresSourceLockManager,
)
from data_update_service.orchestration.artifact_package import FilesystemArtifactStore
from data_update_service.orchestration.commands import RefreshCommand
from data_update_service.orchestration.diff import (
    DatasetDiffReport,
    DatasetSummary,
)
from data_update_service.orchestration.results import RefreshResult
from data_update_service.orchestration.runner import (
    RunnerDependencies,
    run_refresh_job,
)

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
            cursor.execute("DROP TABLE IF EXISTS dataset_channels")
            cursor.execute("DROP TABLE IF EXISTS dataset_versions")
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


def test_runner_persists_dataset_registry_state_in_postgres(
    database_url: str,
    tmp_path: Path,
) -> None:
    command = _runner_command(tmp_path)

    registry = PostgresDatasetRegistry(database_url, initialize_schema=True)

    deps = RunnerDependencies(
        pipeline_runner=_FakePipelineRunner(),
        diff_generator=_FakeDiffGenerator(),
        source_acquirer=None,
        artifact_store=FilesystemArtifactStore(tmp_path / "artifacts"),
        audit_root=tmp_path / "audit",
        job_store=PostgresJobStore(database_url, initialize_schema=True),
        source_locks=PostgresSourceLockManager(
            database_url,
            ttl_seconds=60,
            initialize_schema=True,
        ),
        dataset_registry=registry,
        attempt_store=PostgresAttemptStore(database_url, initialize_schema=True),
    )

    result = run_refresh_job(command, deps)

    assert result.status == "completed"
    assert result.dataset_version is not None

    version = registry.get_dataset_version(result.dataset_version)
    channel = registry.get_channel(source_family="world_bank", channel="staging")

    assert version is not None
    assert version.dataset_version == result.dataset_version
    assert version.source_family == "world_bank"
    assert version.artifact_uri == result.artifact_uri
    assert version.row_count == 2
    assert version.country_count == 2
    assert version.metric_count == 1
    assert version.year_min == 2024
    assert version.year_max == 2024

    assert channel is not None
    assert channel.channel == "staging"
    assert channel.source_family == "world_bank"
    assert channel.dataset_version == result.dataset_version
    assert channel.artifact_uri == result.artifact_uri
    assert channel.promoted_by == "pytest"

    stored_result = deps.job_store.result_for_job(command.job_id)
    attempts = deps.attempt_store.list_attempts(command.job_id)

    assert stored_result is not None
    assert stored_result.status == "completed"
    assert stored_result.dataset_version == result.dataset_version
    assert len(attempts) == 1
    assert attempts[0].status == "completed"


@dataclass(frozen=True, slots=True)
class _FakeProcessingResult:
    ok: bool
    canonical_dataframe: pd.DataFrame
    validation_report: dict[str, Any]
    warnings: list[str]


class _FakePipelineRunner:
    def run(
        self,
        command: RefreshCommand,
        *,
        audit_dir: Path,
        raw_root: Path | None = None,
    ) -> _FakeProcessingResult:
        return _FakeProcessingResult(
            ok=True,
            canonical_dataframe=pd.DataFrame(
                [
                    {
                        "country_code": "ISR",
                        "country_name": "Israel",
                        "metric_id": "gdp_per_capita",
                        "metric_name": "GDP per capita",
                        "value": 100.0,
                        "year": 2024,
                        "unit": "current_usd",
                        "source_name": "pytest",
                        "source_url": "https://example.test",
                        "higher_is_better": True,
                        "category": "economy",
                    },
                    {
                        "country_code": "FRA",
                        "country_name": "France",
                        "metric_id": "gdp_per_capita",
                        "metric_name": "GDP per capita",
                        "value": 120.0,
                        "year": 2024,
                        "unit": "current_usd",
                        "source_name": "pytest",
                        "source_url": "https://example.test",
                        "higher_is_better": True,
                        "category": "economy",
                    },
                ]
            ),
            validation_report={"passed": True},
            warnings=[],
        )


class _FakeDiffGenerator:
    def generate(self, dataframe: pd.DataFrame) -> DatasetDiffReport:
        return DatasetDiffReport(
            summary=DatasetSummary(
                row_count=len(dataframe.index),
                country_count=int(dataframe["country_code"].nunique()),
                metric_count=int(dataframe["metric_id"].nunique()),
                year_min=int(dataframe["year"].min()),
                year_max=int(dataframe["year"].max()),
            ),
            no_changes=False,
            notes=("pytest runner postgres registry coverage",),
        )


def _runner_command(tmp_path: Path) -> RefreshCommand:
    suffix = uuid4().hex[:8]
    manifest_path = tmp_path / "manifest.yaml"
    manifest_path.write_text("sources: []\n", encoding="utf-8")

    return RefreshCommand.create(
        source_family="world_bank",
        manifest_path=manifest_path,
        mode="full_refresh",
        acquisition_mode="local",
        dry_run=False,
        publish=True,
        promote=True,
        promotion_channel="staging",
        requested_by="pytest",
        requested_at=datetime(2026, 1, 1, tzinfo=UTC),
        command_id=f"cmd_runner_postgres_registry_{suffix}",
        job_id=f"job_runner_postgres_registry_{suffix}",
        idempotency_key=f"idem_runner_postgres_registry_{suffix}",
        correlation_id=f"corr_runner_postgres_registry_{suffix}",
    )
