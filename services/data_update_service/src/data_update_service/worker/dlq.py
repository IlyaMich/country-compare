from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from pydantic import ValidationError

from data_update_service.infrastructure.kafka import KafkaConsumer, KafkaMessage
from data_update_service.worker.events import DeadLetterEvent


@dataclass(frozen=True, slots=True)
class DlqMessageRecord:
    topic: str
    key: str | None
    partition: int | None
    offset: int | None
    headers: dict[str, str]
    event: dict[str, Any] | None
    raw_payload: str
    parse_error: str | None = None

    @property
    def is_valid_dead_letter_event(self) -> bool:
        return self.event is not None and self.parse_error is None

    def as_dict(self) -> dict[str, Any]:
        return {
            "topic": self.topic,
            "key": self.key,
            "partition": self.partition,
            "offset": self.offset,
            "headers": self.headers,
            "event": self.event,
            "raw_payload": self.raw_payload,
            "parse_error": self.parse_error,
        }


@dataclass(frozen=True, slots=True)
class DlqInspectionResult:
    messages: list[DlqMessageRecord]
    committed: int
    empty_polls: int

    @property
    def count(self) -> int:
        return len(self.messages)

    def as_dict(self) -> dict[str, Any]:
        return {
            "count": self.count,
            "committed": self.committed,
            "empty_polls": self.empty_polls,
            "messages": [message.as_dict() for message in self.messages],
        }


def inspect_dlq_messages(
    *,
    consumer: KafkaConsumer,
    max_messages: int,
    timeout_seconds: float,
    max_empty_polls: int,
    commit: bool,
) -> DlqInspectionResult:
    if max_messages <= 0:
        raise ValueError("max_messages must be greater than zero")
    if timeout_seconds < 0:
        raise ValueError("timeout_seconds must be greater than or equal to zero")
    if max_empty_polls <= 0:
        raise ValueError("max_empty_polls must be greater than zero")

    records: list[DlqMessageRecord] = []
    committed = 0
    empty_polls = 0

    while len(records) < max_messages and empty_polls < max_empty_polls:
        message = consumer.poll(timeout_seconds=timeout_seconds)
        if message is None:
            empty_polls += 1
            continue

        records.append(parse_dlq_message(message))

        if commit:
            consumer.commit(message)
            committed += 1

    return DlqInspectionResult(
        messages=records,
        committed=committed,
        empty_polls=empty_polls,
    )


def parse_dlq_message(message: KafkaMessage) -> DlqMessageRecord:
    raw_payload = _safe_decode(message.value)

    try:
        event = DeadLetterEvent.model_validate_json(message.value)
    except (ValidationError, ValueError, UnicodeDecodeError) as exc:
        return DlqMessageRecord(
            topic=message.topic,
            key=message.key,
            partition=message.partition,
            offset=message.offset,
            headers=dict(message.headers),
            event=None,
            raw_payload=raw_payload,
            parse_error=str(exc),
        )

    return DlqMessageRecord(
        topic=message.topic,
        key=message.key,
        partition=message.partition,
        offset=message.offset,
        headers=dict(message.headers),
        event=event.model_dump(mode="json"),
        raw_payload=raw_payload,
    )


def _safe_decode(value: bytes) -> str:
    try:
        return value.decode("utf-8")
    except UnicodeDecodeError:
        return value.hex()
