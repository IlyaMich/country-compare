from __future__ import annotations

import json

from data_update_service.infrastructure.kafka import InMemoryKafkaProducer
from data_update_service.orchestration.commands import RefreshCommand
from data_update_service.worker.publisher import publish_refresh_command


def test_publish_refresh_command_uses_source_family_as_key() -> None:
    producer = InMemoryKafkaProducer()
    command = RefreshCommand.create(
        source_family="world_bank",
        manifest_path="config/source_manifests/world_bank_real_data.yaml",
        dry_run=True,
        publish=False,
    )

    metadata = publish_refresh_command(
        command=command,
        producer=producer,
        topic="commands",
    )

    assert metadata.topic == "commands"
    assert metadata.key == "world_bank"
    assert metadata.command_id == command.command_id
    assert len(producer.messages) == 1
    message = producer.messages[0]
    assert message.topic == "commands"
    assert message.key == "world_bank"
    assert message.headers == {"message_type": "RefreshCommand"}
    payload = json.loads(message.value.decode("utf-8"))
    assert payload["command_id"] == command.command_id
    assert payload["source_family"] == "world_bank"
