from __future__ import annotations

from datetime import UTC, datetime

from data_update_service.infrastructure.kafka import (
    InMemoryKafkaConsumer,
    InMemoryKafkaProducer,
    KafkaMessage,
)
from data_update_service.orchestration.commands import RefreshCommand
from data_update_service.worker.handlers import WorkerEventPublisher
from data_update_service.worker.retry_relay import (
    RetryCommandRelayHandler,
    RetryCommandRelayWorker,
    RetryDelayPolicy,
)


def test_retry_relay_forwards_retry_command_to_command_topic() -> None:
    command = _command(attempt=2)
    producer = InMemoryKafkaProducer()
    sleeps: list[float] = []

    handler = RetryCommandRelayHandler(
        producer=producer,
        command_topic="commands",
        event_publisher=WorkerEventPublisher(
            producer=producer,
            status_topic="status",
            dlq_topic="dlq",
            retry_5m_topic="retry.5m",
            retry_1h_topic="retry.1h",
        ),
        delay_policy=RetryDelayPolicy(
            retry_5m_topic="retry.5m",
            retry_1h_topic="retry.1h",
            retry_5m_delay_seconds=0,
            retry_1h_delay_seconds=0,
            sleep=sleeps.append,
        ),
    )

    result = handler.process_message(
        KafkaMessage(
            topic="retry.5m",
            key="world_bank",
            value=command.model_dump_json().encode("utf-8"),
        )
    )

    assert result.status == "forwarded"
    assert result.ack is True
    assert result.command_topic == "commands"
    assert result.job_id == command.job_id

    assert len(producer.messages) == 1
    published = producer.messages[0]
    assert published.topic == "commands"
    assert published.key == "world_bank"
    assert published.headers["retry_relayed"] == "true"
    assert published.headers["attempt"] == "2"
    assert published.headers["source_retry_topic"] == "retry.5m"

    forwarded = RefreshCommand.model_validate_json(published.value)
    assert forwarded.job_id == command.job_id
    assert forwarded.command_id == command.command_id
    assert forwarded.attempt == 2


def test_retry_relay_uses_topic_delay_policy() -> None:
    command = _command(attempt=3)
    producer = InMemoryKafkaProducer()
    sleeps: list[float] = []

    handler = RetryCommandRelayHandler(
        producer=producer,
        command_topic="commands",
        event_publisher=WorkerEventPublisher(
            producer=producer,
            status_topic="status",
            dlq_topic="dlq",
            retry_5m_topic="retry.5m",
            retry_1h_topic="retry.1h",
        ),
        delay_policy=RetryDelayPolicy(
            retry_5m_topic="retry.5m",
            retry_1h_topic="retry.1h",
            retry_5m_delay_seconds=300,
            retry_1h_delay_seconds=3600,
            sleep=sleeps.append,
        ),
    )

    handler.process_message(
        KafkaMessage(
            topic="retry.1h",
            key="world_bank",
            value=command.model_dump_json().encode("utf-8"),
        )
    )

    assert sleeps == [3600]


def test_retry_relay_sends_invalid_retry_command_to_dlq() -> None:
    producer = InMemoryKafkaProducer()

    handler = RetryCommandRelayHandler(
        producer=producer,
        command_topic="commands",
        event_publisher=WorkerEventPublisher(
            producer=producer,
            status_topic="status",
            dlq_topic="dlq",
            retry_5m_topic="retry.5m",
            retry_1h_topic="retry.1h",
        ),
        delay_policy=RetryDelayPolicy(
            retry_5m_topic="retry.5m",
            retry_1h_topic="retry.1h",
            retry_5m_delay_seconds=0,
            retry_1h_delay_seconds=0,
        ),
    )

    result = handler.process_message(
        KafkaMessage(
            topic="retry.5m",
            key="world_bank",
            value=b"{bad json",
        )
    )

    assert result.status == "invalid_retry_command_dlq"
    assert result.ack is True
    assert result.error_code == "invalid_retry_command"

    assert len(producer.messages) == 1
    assert producer.messages[0].topic == "dlq"


def test_retry_relay_worker_commits_after_forwarding() -> None:
    command = _command(attempt=2)
    message = KafkaMessage(
        topic="retry.5m",
        key="world_bank",
        value=command.model_dump_json().encode("utf-8"),
    )
    consumer = InMemoryKafkaConsumer([message])
    producer = InMemoryKafkaProducer()

    handler = RetryCommandRelayHandler(
        producer=producer,
        command_topic="commands",
        event_publisher=WorkerEventPublisher(
            producer=producer,
            status_topic="status",
            dlq_topic="dlq",
            retry_5m_topic="retry.5m",
            retry_1h_topic="retry.1h",
        ),
        delay_policy=RetryDelayPolicy(
            retry_5m_topic="retry.5m",
            retry_1h_topic="retry.1h",
            retry_5m_delay_seconds=0,
            retry_1h_delay_seconds=0,
        ),
    )
    worker = RetryCommandRelayWorker(consumer=consumer, handler=handler)

    processed = worker.run_once()

    assert processed is True
    assert consumer.committed_messages == [message]
    assert producer.messages[0].topic == "commands"


def _command(*, attempt: int) -> RefreshCommand:
    return RefreshCommand.create(
        source_family="world_bank",
        manifest_path="config/source_manifests/world_bank_real_data.yaml",
        mode="full_refresh",
        acquisition_mode="remote",
        dry_run=True,
        publish=False,
        promote=False,
        promotion_channel="staging",
        requested_by="pytest",
        requested_at=datetime(2026, 1, 1, tzinfo=UTC),
        command_id="cmd_retry_relay_unit",
        job_id="job_retry_relay_unit",
        idempotency_key="idem_retry_relay_unit",
        correlation_id="corr_retry_relay_unit",
        attempt=attempt,
        max_attempts=3,
    )
