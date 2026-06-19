from __future__ import annotations

from datetime import UTC, datetime

import pytest

from data_update_service.infrastructure.kafka import InMemoryKafkaConsumer, KafkaMessage
from data_update_service.worker.dlq import inspect_dlq_messages, parse_dlq_message
from data_update_service.worker.events import DeadLetterEvent


def test_parse_dlq_message_parses_dead_letter_event() -> None:
    event = _dead_letter_event()
    message = KafkaMessage(
        topic="dlq",
        key="job_1",
        value=event.model_dump_json().encode("utf-8"),
        headers={"event_type": "DeadLetterEvent"},
        partition=0,
        offset=42,
    )

    record = parse_dlq_message(message)

    assert record.topic == "dlq"
    assert record.key == "job_1"
    assert record.partition == 0
    assert record.offset == 42
    assert record.headers == {"event_type": "DeadLetterEvent"}
    assert record.parse_error is None
    assert record.event is not None
    assert record.event["error_code"] == "validation_failed"
    assert record.event["job_id"] == "job_1"


def test_parse_dlq_message_preserves_invalid_payload() -> None:
    message = KafkaMessage(
        topic="dlq",
        key="bad",
        value=b"{bad json",
    )

    record = parse_dlq_message(message)

    assert record.event is None
    assert record.parse_error is not None
    assert record.raw_payload == "{bad json"


def test_inspect_dlq_messages_reads_and_commits_when_requested() -> None:
    event = _dead_letter_event()
    message = KafkaMessage(
        topic="dlq",
        key="job_1",
        value=event.model_dump_json().encode("utf-8"),
    )
    consumer = InMemoryKafkaConsumer([message])

    result = inspect_dlq_messages(
        consumer=consumer,
        max_messages=10,
        timeout_seconds=0,
        max_empty_polls=1,
        commit=True,
    )

    assert result.count == 1
    assert result.committed == 1
    assert consumer.committed_messages == [message]


def test_inspect_dlq_messages_does_not_commit_by_default() -> None:
    event = _dead_letter_event()
    message = KafkaMessage(
        topic="dlq",
        key="job_1",
        value=event.model_dump_json().encode("utf-8"),
    )
    consumer = InMemoryKafkaConsumer([message])

    result = inspect_dlq_messages(
        consumer=consumer,
        max_messages=10,
        timeout_seconds=0,
        max_empty_polls=1,
        commit=False,
    )

    assert result.count == 1
    assert result.committed == 0
    assert consumer.committed_messages == []


def test_inspect_dlq_messages_rejects_invalid_max_messages() -> None:
    consumer = InMemoryKafkaConsumer([])

    with pytest.raises(ValueError, match="max_messages"):
        inspect_dlq_messages(
            consumer=consumer,
            max_messages=0,
            timeout_seconds=0,
            max_empty_polls=1,
            commit=False,
        )


def _dead_letter_event() -> DeadLetterEvent:
    return DeadLetterEvent(
        event_id="evt_dlq_test",
        original_topic="commands",
        original_key="world_bank",
        job_id="job_1",
        command_id="cmd_1",
        source_family="world_bank",
        error_code="validation_failed",
        error_message="Validation failed",
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
        raw_payload='{"bad": "payload"}',
    )
