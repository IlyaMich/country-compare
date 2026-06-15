from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal
from uuid import uuid4

from pydantic import ValidationError

from data_update_service.infrastructure.kafka import (
    ConfluentKafkaConsumer,
    ConfluentKafkaProducer,
    KafkaConsumer,
    KafkaMessage,
    KafkaProducer,
)
from data_update_service.orchestration.commands import RefreshCommand
from data_update_service.settings import DataUpdateSettings
from data_update_service.worker.events import DeadLetterEvent
from data_update_service.worker.handlers import WorkerEventPublisher

RetryRelayStatus = Literal["forwarded", "invalid_retry_command_dlq"]


@dataclass(frozen=True, slots=True)
class RetryRelayResult:
    status: RetryRelayStatus
    ack: bool
    retry_topic: str
    command_topic: str | None = None
    job_id: str | None = None
    command_id: str | None = None
    error_code: str | None = None
    error_message: str | None = None


@dataclass(frozen=True, slots=True)
class RetryDelayPolicy:
    retry_5m_topic: str
    retry_1h_topic: str
    retry_5m_delay_seconds: int
    retry_1h_delay_seconds: int
    sleep: Callable[[float], None] = time.sleep

    def delay_for_topic(self, topic: str) -> int:
        if topic == self.retry_5m_topic:
            return self.retry_5m_delay_seconds
        if topic == self.retry_1h_topic:
            return self.retry_1h_delay_seconds
        return 0

    def wait_for_topic(self, topic: str) -> None:
        delay_seconds = self.delay_for_topic(topic)
        if delay_seconds > 0:
            self.sleep(delay_seconds)


class RetryCommandRelayHandler:
    def __init__(
        self,
        *,
        producer: KafkaProducer,
        command_topic: str,
        event_publisher: WorkerEventPublisher,
        delay_policy: RetryDelayPolicy,
    ) -> None:
        self._producer = producer
        self._command_topic = command_topic
        self._event_publisher = event_publisher
        self._delay_policy = delay_policy

    def process_message(self, message: KafkaMessage) -> RetryRelayResult:
        try:
            command = RefreshCommand.model_validate_json(message.value)
        except (ValidationError, ValueError, UnicodeDecodeError) as exc:
            self._event_publisher.publish_dlq(
                _make_invalid_retry_dlq_event(message=message, error_message=str(exc))
            )
            return RetryRelayResult(
                status="invalid_retry_command_dlq",
                ack=True,
                retry_topic=message.topic,
                error_code="invalid_retry_command",
                error_message=str(exc),
            )

        self._delay_policy.wait_for_topic(message.topic)

        self._producer.send(
            topic=self._command_topic,
            key=command.source_family,
            value=command.model_dump_json().encode("utf-8"),
            headers={
                "event_type": "RefreshCommand",
                "retry_relayed": "true",
                "attempt": str(command.attempt),
                "max_attempts": str(command.max_attempts),
                "source_retry_topic": message.topic,
            },
        )
        self._producer.flush()

        return RetryRelayResult(
            status="forwarded",
            ack=True,
            retry_topic=message.topic,
            command_topic=self._command_topic,
            job_id=command.job_id,
            command_id=command.command_id,
        )


class RetryCommandRelayWorker:
    def __init__(
        self,
        *,
        consumer: KafkaConsumer,
        handler: RetryCommandRelayHandler,
    ) -> None:
        self._consumer = consumer
        self._handler = handler

    def run_once(self, *, timeout_seconds: float = 1.0) -> bool:
        message = self._consumer.poll(timeout_seconds=timeout_seconds)
        if message is None:
            return False

        result = self._handler.process_message(message)
        if result.ack:
            self._consumer.commit(message)

        return True

    def run_forever(self, *, timeout_seconds: float = 1.0) -> None:
        try:
            while True:
                self.run_once(timeout_seconds=timeout_seconds)
        finally:
            self._consumer.close()


def build_retry_relay_worker(
    settings: DataUpdateSettings | None = None,
) -> RetryCommandRelayWorker:
    resolved = settings or DataUpdateSettings.from_env()

    producer = ConfluentKafkaProducer(
        bootstrap_servers=resolved.kafka_bootstrap_servers,
    )
    consumer = ConfluentKafkaConsumer(
        bootstrap_servers=resolved.kafka_bootstrap_servers,
        group_id=resolved.kafka_retry_consumer_group,
        topics=[
            resolved.kafka_retry_5m_topic,
            resolved.kafka_retry_1h_topic,
        ],
    )
    event_publisher = WorkerEventPublisher(
        producer=producer,
        status_topic=resolved.kafka_status_topic,
        dlq_topic=resolved.kafka_dlq_topic,
        retry_5m_topic=resolved.kafka_retry_5m_topic,
        retry_1h_topic=resolved.kafka_retry_1h_topic,
    )
    handler = RetryCommandRelayHandler(
        producer=producer,
        command_topic=resolved.kafka_command_topic,
        event_publisher=event_publisher,
        delay_policy=RetryDelayPolicy(
            retry_5m_topic=resolved.kafka_retry_5m_topic,
            retry_1h_topic=resolved.kafka_retry_1h_topic,
            retry_5m_delay_seconds=resolved.retry_5m_delay_seconds,
            retry_1h_delay_seconds=resolved.retry_1h_delay_seconds,
        ),
    )

    return RetryCommandRelayWorker(consumer=consumer, handler=handler)


def main() -> None:
    worker = build_retry_relay_worker()
    worker.run_forever()


def _make_invalid_retry_dlq_event(
    *,
    message: KafkaMessage,
    error_message: str,
) -> DeadLetterEvent:
    return DeadLetterEvent(
        event_id=f"evt_dlq_{uuid4().hex}",
        original_topic=message.topic,
        original_key=message.key,
        error_code="invalid_retry_command",
        error_message=error_message,
        created_at=datetime.now(tz=UTC),
        raw_payload=_safe_payload(message.value),
    )


def _safe_payload(value: bytes) -> str:
    try:
        return value.decode("utf-8")
    except UnicodeDecodeError:
        return value.hex()


if __name__ == "__main__":  # pragma: no cover - module entrypoint
    main()
