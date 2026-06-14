from __future__ import annotations

from data_update_service.infrastructure.kafka import (
    InMemoryKafkaConsumer,
    InMemoryKafkaProducer,
    KafkaMessage,
)
from data_update_service.orchestration.commands import RefreshCommand
from data_update_service.orchestration.results import RefreshResult
from data_update_service.worker.consumer import RefreshWorker
from data_update_service.worker.handlers import (
    RefreshCommandWorkerHandler,
    WorkerEventPublisher,
)


def test_refresh_worker_commits_after_handler_ack(tmp_path) -> None:
    manifest = tmp_path / "manifest.yaml"
    manifest.write_text("sources: []\n", encoding="utf-8")
    command = RefreshCommand.create(
        source_family="world_bank",
        manifest_path=manifest,
        dry_run=True,
        publish=False,
    )
    message = KafkaMessage(
        topic="commands-topic",
        key="world_bank",
        value=command.model_dump_json().encode("utf-8"),
    )
    consumer = InMemoryKafkaConsumer([message])
    producer = InMemoryKafkaProducer()

    def fake_runner(command_arg, dependencies):
        del dependencies
        return RefreshResult(
            job_id=command_arg.job_id,
            command_id=command_arg.command_id,
            source_family=command_arg.source_family,
            status="dry_run_completed",
            row_count=1,
            country_count=1,
            metric_count=1,
        )

    handler = RefreshCommandWorkerHandler(
        event_publisher=WorkerEventPublisher(
            producer=producer,
            status_topic="status-topic",
            dlq_topic="dlq-topic",
        ),
        runner=fake_runner,
    )
    worker = RefreshWorker(consumer=consumer, handler=handler)

    assert worker.run_once() is True
    assert consumer.committed_messages == [message]
    assert worker.run_once() is False


def test_refresh_worker_run_until_idle_returns_stats() -> None:
    consumer = InMemoryKafkaConsumer([])
    producer = InMemoryKafkaProducer()
    handler = RefreshCommandWorkerHandler(
        event_publisher=WorkerEventPublisher(
            producer=producer,
            status_topic="status-topic",
            dlq_topic="dlq-topic",
        )
    )
    worker = RefreshWorker(consumer=consumer, handler=handler)

    stats = worker.run_until_idle(max_empty_polls=2)

    assert stats.polled == 0
    assert stats.committed == 0
    assert stats.empty_polls == 2
