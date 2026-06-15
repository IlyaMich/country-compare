from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path

from data_update_service.cli import inspect_dlq_from_args
from data_update_service.infrastructure.kafka import InMemoryKafkaConsumer, KafkaMessage
from data_update_service.worker.events import DeadLetterEvent


def test_inspect_dlq_from_args_writes_json_output_file(
    tmp_path: Path,
    capsys,
) -> None:
    output_json = tmp_path / "dlq.json"
    event = _dead_letter_event()
    message = KafkaMessage(
        topic="dlq-topic",
        key="job_1",
        value=event.model_dump_json().encode("utf-8"),
        partition=0,
        offset=7,
    )
    consumer = InMemoryKafkaConsumer([message])
    args = argparse.Namespace(
        kafka_bootstrap_servers="unused:9092",
        kafka_dlq_topic="dlq-topic",
        consumer_group="dlq-inspector",
        max_messages=10,
        timeout_seconds=0,
        max_empty_polls=1,
        commit=False,
        format="json",
        output_json=output_json,
    )

    exit_code = inspect_dlq_from_args(args, consumer=consumer)

    assert exit_code == 0
    assert consumer.committed_messages == []

    printed = json.loads(capsys.readouterr().out)
    written = json.loads(output_json.read_text(encoding="utf-8"))

    assert printed == written
    assert written["topic"] == "dlq-topic"
    assert written["consumer_group"] == "dlq-inspector"
    assert written["count"] == 1
    assert written["messages"][0]["event"]["error_code"] == "validation_failed"


def test_inspect_dlq_from_args_commits_when_requested(capsys) -> None:
    event = _dead_letter_event()
    message = KafkaMessage(
        topic="dlq-topic",
        key="job_1",
        value=event.model_dump_json().encode("utf-8"),
    )
    consumer = InMemoryKafkaConsumer([message])
    args = argparse.Namespace(
        kafka_bootstrap_servers="unused:9092",
        kafka_dlq_topic="dlq-topic",
        consumer_group="dlq-inspector",
        max_messages=10,
        timeout_seconds=0,
        max_empty_polls=1,
        commit=True,
        format="text",
        output_json=None,
    )

    exit_code = inspect_dlq_from_args(args, consumer=consumer)

    assert exit_code == 0
    assert consumer.committed_messages == [message]
    assert "DLQ topic: dlq-topic" in capsys.readouterr().out


def _dead_letter_event() -> DeadLetterEvent:
    return DeadLetterEvent(
        event_id="evt_dlq_cli_test",
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
