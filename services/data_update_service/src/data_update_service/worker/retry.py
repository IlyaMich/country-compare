from __future__ import annotations

from dataclasses import dataclass

from data_update_service.orchestration.commands import RefreshCommand
from data_update_service.orchestration.results import RefreshResult


@dataclass(frozen=True, slots=True)
class RetryDecision:
    should_retry: bool
    retry_topic: str | None
    next_attempt: int | None
    reason: str


def decide_retry(
    *,
    command: RefreshCommand,
    result: RefreshResult,
    retry_5m_topic: str,
    retry_1h_topic: str,
) -> RetryDecision:
    if result.status != "failed_retryable":
        return RetryDecision(
            should_retry=False,
            retry_topic=None,
            next_attempt=None,
            reason=f"result status is {result.status}",
        )

    if command.attempt >= command.max_attempts:
        return RetryDecision(
            should_retry=False,
            retry_topic=None,
            next_attempt=None,
            reason="max attempts reached",
        )

    next_attempt = command.attempt + 1
    retry_topic = retry_5m_topic if command.attempt == 1 else retry_1h_topic

    return RetryDecision(
        should_retry=True,
        retry_topic=retry_topic,
        next_attempt=next_attempt,
        reason=result.error_code or "retryable refresh failure",
    )


def make_retry_command(command: RefreshCommand) -> RefreshCommand:
    payload = command.model_dump()
    payload["attempt"] = command.attempt + 1
    return RefreshCommand.model_validate(payload)
