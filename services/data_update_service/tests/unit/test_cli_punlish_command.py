from __future__ import annotations

import argparse
import json
from pathlib import Path

from data_update_service.cli import publish_command_from_args
from data_update_service.infrastructure.kafka import InMemoryKafkaProducer


def test_publish_command_from_args_writes_kafka_message_and_output_file(
    tmp_path: Path,
) -> None:
    producer = InMemoryKafkaProducer()
    output_json = tmp_path / "published_command.json"
    args = argparse.Namespace(
        source_family="world_bank",
        manifest_path=Path("config/source_manifests/world_bank_real_data.yaml"),
        mode="full_refresh",
        dry_run=True,
        publish=False,
        promote=False,
        promotion_channel="staging",
        requested_by="test",
        max_attempts=3,
        kafka_bootstrap_servers="unused:9092",
        kafka_command_topic="commands",
        output_json=output_json,
    )

    exit_code = publish_command_from_args(args, producer=producer)

    assert exit_code == 0
    assert len(producer.messages) == 1
    assert producer.messages[0].topic == "commands"
    assert producer.messages[0].key == "world_bank"
    output_payload = json.loads(output_json.read_text(encoding="utf-8"))
    assert output_payload["published"] is True
    assert output_payload["topic"] == "commands"
    assert output_payload["source_family"] == "world_bank"
