from __future__ import annotations

from datetime import UTC, datetime

from data_update_service.orchestration.commands import RefreshCommand
from data_update_service.orchestration.results import RefreshResult
from data_update_service.worker.retry import decide_retry, make_retry_command


def test_attempt_one_retryable_failure_schedules_retry_5m() -> None:
    command = _command(attempt=1, max_attempts=3)
    result = _retryable_result(command)

    decision = decide_retry(
        command=command,
        result=result,
        retry_5m_topic="retry.5m",
        retry_1h_topic="retry.1h",
    )

    assert decision.should_retry is True
    assert decision.retry_topic == "retry.5m"
    assert decision.next_attempt == 2


def test_attempt_two_retryable_failure_schedules_retry_1h() -> None:
    command = _command(attempt=2, max_attempts=3)
    result = _retryable_result(command)

    decision = decide_retry(
        command=command,
        result=result,
        retry_5m_topic="retry.5m",
        retry_1h_topic="retry.1h",
    )

    assert decision.should_retry is True
    assert decision.retry_topic == "retry.1h"
    assert decision.next_attempt == 3


def test_max_attempt_retryable_failure_does_not_schedule_retry() -> None:
    command = _command(attempt=3, max_attempts=3)
    result = _retryable_result(command)

    decision = decide_retry(
        command=command,
        result=result,
        retry_5m_topic="retry.5m",
        retry_1h_topic="retry.1h",
    )

    assert decision.should_retry is False
    assert decision.retry_topic is None
    assert decision.next_attempt is None


def test_non_retryable_failure_does_not_schedule_retry() -> None:
    command = _command(attempt=1, max_attempts=3)
    result = RefreshResult(
        job_id=command.job_id,
        command_id=command.command_id,
        source_family=command.source_family,
        status="failed_non_retryable",
        error_code="validation_failed",
        error_message="validation failed",
    )

    decision = decide_retry(
        command=command,
        result=result,
        retry_5m_topic="retry.5m",
        retry_1h_topic="retry.1h",
    )

    assert decision.should_retry is False


def test_make_retry_command_increments_attempt_and_preserves_identity() -> None:
    command = _command(attempt=1, max_attempts=3)

    retry_command = make_retry_command(command)

    assert retry_command.attempt == 2
    assert retry_command.max_attempts == command.max_attempts
    assert retry_command.job_id == command.job_id
    assert retry_command.command_id == command.command_id
    assert retry_command.idempotency_key == command.idempotency_key


def _command(*, attempt: int, max_attempts: int) -> RefreshCommand:
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
        command_id="cmd_retry_unit",
        job_id="job_retry_unit",
        idempotency_key="idem_retry_unit",
        correlation_id="corr_retry_unit",
        attempt=attempt,
        max_attempts=max_attempts,
    )


def _retryable_result(command: RefreshCommand) -> RefreshResult:
    return RefreshResult(
        job_id=command.job_id,
        command_id=command.command_id,
        source_family=command.source_family,
        status="failed_retryable",
        error_code="source_acquisition_retryable",
        error_message="temporary upstream failure",
    )
