from __future__ import annotations

from datetime import UTC, datetime

from data_update_service.infrastructure.attempt_store import InMemoryAttemptStore
from data_update_service.orchestration.commands import RefreshCommand


def test_in_memory_attempt_store_records_attempt_lifecycle() -> None:
    command = RefreshCommand.create(
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
        command_id="cmd_attempt_unit",
        job_id="job_attempt_unit",
        idempotency_key="idem_attempt_unit",
        correlation_id="corr_attempt_unit",
    )

    store = InMemoryAttemptStore()

    started = store.start_attempt(command, worker_id="unit-worker")
    assert started.status == "running"
    assert started.worker_id == "unit-worker"
    assert started.finished_at is None

    finished = store.finish_attempt(
        started.attempt_id,
        status="dry_run_completed",
    )

    assert finished.status == "dry_run_completed"
    assert finished.finished_at is not None

    attempts = store.list_attempts(command.job_id)

    assert attempts == [finished]
