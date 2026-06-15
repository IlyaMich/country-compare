from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal
from uuid import uuid4

from pydantic import ValidationError

from data_update_service.infrastructure.kafka import KafkaMessage, KafkaProducer
from data_update_service.orchestration.commands import RefreshCommand
from data_update_service.orchestration.results import RefreshResult
from data_update_service.orchestration.runner import RunnerDependencies, run_refresh_job
from data_update_service.worker.events import (
    DeadLetterEvent,
    RefreshStatusEvent,
    make_result_status_event,
    make_status_event,
)
from data_update_service.worker.retry import decide_retry, make_retry_command

WorkerMessageStatus = Literal[
    "processed",
    "invalid_command_dlq",
    "retry_scheduled",
    "failed_result_dlq",
]


@dataclass(frozen=True, slots=True)
class WorkerProcessResult:
    status: WorkerMessageStatus
    ack: bool
    job_id: str | None = None
    command_id: str | None = None
    error_code: str | None = None
    error_message: str | None = None
    retry_topic: str | None = None


class WorkerEventPublisher:
    def __init__(
        self,
        *,
        producer: KafkaProducer,
        status_topic: str,
        dlq_topic: str,
        retry_5m_topic: str = "country-compare.data-refresh.retry.5m.v1",
        retry_1h_topic: str = "country-compare.data-refresh.retry.1h.v1",
    ) -> None:
        self._producer = producer
        self._status_topic = status_topic
        self._dlq_topic = dlq_topic
        self._retry_5m_topic = retry_5m_topic
        self._retry_1h_topic = retry_1h_topic

    @property
    def retry_5m_topic(self) -> str:
        return self._retry_5m_topic

    @property
    def retry_1h_topic(self) -> str:
        return self._retry_1h_topic

    def publish_status(self, event: RefreshStatusEvent) -> None:
        self._producer.send(
            topic=self._status_topic,
            key=event.job_id,
            value=event.model_dump_json().encode("utf-8"),
            headers={"event_type": "RefreshStatusEvent"},
        )
        self._producer.flush()

    def publish_dlq(self, event: DeadLetterEvent) -> None:
        self._producer.send(
            topic=self._dlq_topic,
            key=event.job_id or event.original_key,
            value=event.model_dump_json().encode("utf-8"),
            headers={"event_type": "DeadLetterEvent"},
        )
        self._producer.flush()

    def publish_retry_command(
        self,
        *,
        topic: str,
        command: RefreshCommand,
        reason: str,
    ) -> None:
        self._producer.send(
            topic=topic,
            key=command.source_family,
            value=command.model_dump_json().encode("utf-8"),
            headers={
                "event_type": "RefreshCommand",
                "retry_reason": reason,
                "attempt": str(command.attempt),
                "max_attempts": str(command.max_attempts),
            },
        )
        self._producer.flush()


class RefreshCommandWorkerHandler:
    def __init__(
        self,
        *,
        event_publisher: WorkerEventPublisher,
        dependencies: RunnerDependencies | None = None,
        runner: Callable[
            [RefreshCommand, RunnerDependencies | None], RefreshResult
        ] = run_refresh_job,
    ) -> None:
        self._event_publisher = event_publisher
        self._dependencies = dependencies
        self._runner = runner

    def process_message(self, message: KafkaMessage) -> WorkerProcessResult:
        try:
            command = RefreshCommand.model_validate_json(message.value)
        except (ValidationError, ValueError, UnicodeDecodeError) as exc:
            self._event_publisher.publish_dlq(
                _make_invalid_command_dlq_event(message=message, error_message=str(exc))
            )
            return WorkerProcessResult(
                status="invalid_command_dlq",
                ack=True,
                error_code="invalid_refresh_command",
                error_message=str(exc),
            )

        self._event_publisher.publish_status(
            make_status_event(
                command=command,
                status="accepted",
                message="Refresh command accepted by data-update worker",
                details={
                    "attempt": command.attempt,
                    "max_attempts": command.max_attempts,
                },
            )
        )

        result = self._runner(command, self._dependencies)
        self._event_publisher.publish_status(
            make_result_status_event(command=command, result=result)
        )

        if result.status == "failed_retryable":
            decision = decide_retry(
                command=command,
                result=result,
                retry_5m_topic=self._event_publisher.retry_5m_topic,
                retry_1h_topic=self._event_publisher.retry_1h_topic,
            )

            if decision.should_retry and decision.retry_topic is not None:
                retry_command = make_retry_command(command)

                if (
                    self._dependencies is not None
                    and self._dependencies.job_store is not None
                ):
                    self._dependencies.job_store.update_status(
                        command.job_id,
                        "retry_scheduled",
                    )

                self._event_publisher.publish_status(
                    make_status_event(
                        command=command,
                        status="retry_scheduled",
                        message=(
                            "Refresh job retry scheduled "
                            f"for attempt {retry_command.attempt} of {retry_command.max_attempts}"
                        ),
                        details={
                            "current_attempt": command.attempt,
                            "next_attempt": retry_command.attempt,
                            "max_attempts": retry_command.max_attempts,
                            "retry_topic": decision.retry_topic,
                            "reason": decision.reason,
                            "error_code": result.error_code,
                            "error_message": result.error_message,
                        },
                    )
                )
                self._event_publisher.publish_retry_command(
                    topic=decision.retry_topic,
                    command=retry_command,
                    reason=decision.reason,
                )

                return WorkerProcessResult(
                    status="retry_scheduled",
                    ack=True,
                    job_id=command.job_id,
                    command_id=command.command_id,
                    error_code=result.error_code,
                    error_message=result.error_message,
                    retry_topic=decision.retry_topic,
                )

        if result.status in {"failed_non_retryable", "failed_retryable"}:
            self._event_publisher.publish_dlq(
                _make_failed_result_dlq_event(
                    message=message,
                    command=command,
                    result=result,
                )
            )
            return WorkerProcessResult(
                status="failed_result_dlq",
                ack=True,
                job_id=command.job_id,
                command_id=command.command_id,
                error_code=result.error_code,
                error_message=result.error_message,
            )

        return WorkerProcessResult(
            status="processed",
            ack=True,
            job_id=command.job_id,
            command_id=command.command_id,
        )


def _make_invalid_command_dlq_event(
    *,
    message: KafkaMessage,
    error_message: str,
) -> DeadLetterEvent:
    return DeadLetterEvent(
        event_id=f"evt_dlq_{uuid4().hex}",
        original_topic=message.topic,
        original_key=message.key,
        error_code="invalid_refresh_command",
        error_message=error_message,
        created_at=datetime.now(tz=UTC),
        raw_payload=_safe_payload(message.value),
    )


def _make_failed_result_dlq_event(
    *,
    message: KafkaMessage,
    command: RefreshCommand,
    result: RefreshResult,
) -> DeadLetterEvent:
    return DeadLetterEvent(
        event_id=f"evt_dlq_{uuid4().hex}",
        original_topic=message.topic,
        original_key=message.key,
        job_id=command.job_id,
        command_id=command.command_id,
        source_family=command.source_family,
        error_code=result.error_code or result.status,
        error_message=result.error_message
        or f"Refresh job ended with status {result.status}",
        created_at=datetime.now(tz=UTC),
        raw_payload=_safe_payload(message.value),
        command=command.model_dump(mode="json"),
        result=result.model_dump(mode="json", exclude_none=True),
    )


def _safe_payload(value: bytes) -> str:
    try:
        return value.decode("utf-8")
    except UnicodeDecodeError:
        return value.hex()
