from __future__ import annotations

import argparse
import json
from pathlib import Path

from data_update_service.cli import publish_invalid_command_from_args
from data_update_service.infrastructure.kafka import InMemoryKafkaProducer


def test_publish_invalid_command_from_args_writes_invalid_kafka_message_and_output_file(
    tmp_path: Path,
) -> None:
    producer = InMemoryKafkaProducer()
    output_json = tmp_path / "published_invalid_command.json"

    args = argparse.Namespace(
        source_family="world_bank",
        payload='{"bad": "payload"}',
        kafka_bootstrap_servers="unused:9092",
        kafka_command_topic="commands",
        output_json=output_json,
    )

    exit_code = publish_invalid_command_from_args(args, producer=producer)

    assert exit_code == 0
    assert len(producer.messages) == 1

    message = producer.messages[0]
    assert message.topic == "commands"
    assert message.key == "world_bank"
    assert message.value == b'{"bad": "payload"}'
    assert message.headers == {
        "message_type": "InvalidRefreshCommand",
        "smoke_test": "true",
    }

    output_payload = json.loads(output_json.read_text(encoding="utf-8"))
    assert output_payload["published"] is True
    assert output_payload["topic"] == "commands"
    assert output_payload["key"] == "world_bank"
    assert output_payload["expected_worker_result"] == "invalid_command_dlq"
    assert output_payload["expected_dlq_error_code"] == "invalid_refresh_command"
