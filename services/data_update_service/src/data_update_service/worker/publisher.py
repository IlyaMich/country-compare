from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from data_update_service.infrastructure.kafka import KafkaProducer
from data_update_service.orchestration.commands import RefreshCommand


@dataclass(frozen=True, slots=True)
class PublishedCommandMetadata:
    topic: str
    key: str
    command_id: str
    job_id: str
    source_family: str


def publish_refresh_command(
    *,
    command: RefreshCommand,
    producer: KafkaProducer,
    topic: str,
    headers: Mapping[str, str] | None = None,
) -> PublishedCommandMetadata:
    """Publish a refresh command to the Kafka command topic.

    This helper is deliberately small so the CLI, future admin API, and tests can
    all use the same serialization and keying behavior.
    """

    key = command.source_family
    producer.send(
        topic=topic,
        key=key,
        value=command.model_dump_json().encode("utf-8"),
        headers={"message_type": "RefreshCommand", **dict(headers or {})},
    )
    producer.flush()
    return PublishedCommandMetadata(
        topic=topic,
        key=key,
        command_id=command.command_id,
        job_id=command.job_id,
        source_family=command.source_family,
    )
