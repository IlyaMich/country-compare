from __future__ import annotations

from data_update_service.orchestration.results import RefreshResult


def test_refresh_result_ok_for_terminal_success() -> None:
    result = RefreshResult(
        job_id="job-1",
        command_id="cmd-1",
        source_family="world_bank",
        status="dry_run_completed",
    )

    assert result.ok is True


def test_refresh_result_not_ok_for_failure() -> None:
    result = RefreshResult(
        job_id="job-1",
        command_id="cmd-1",
        source_family="world_bank",
        status="failed_non_retryable",
        error_code="boom",
        error_message="failed",
    )

    assert result.ok is False
