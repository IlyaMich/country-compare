from __future__ import annotations

from dataclasses import dataclass, replace

from data_update_service.infrastructure.dataset_event_publisher import (
    KafkaDatasetEventPublisher,
)
from data_update_service.infrastructure.kafka import (
    ConfluentKafkaConsumer,
    ConfluentKafkaProducer,
    KafkaConsumer,
)
from data_update_service.orchestration.runner import RunnerDependencies
from data_update_service.settings import DataUpdateSettings
from data_update_service.worker.handlers import (
    RefreshCommandWorkerHandler,
    WorkerEventPublisher,
)


@dataclass(frozen=True, slots=True)
class WorkerRunStats:
    polled: int = 0
    committed: int = 0
    empty_polls: int = 0


class RefreshWorker:
    def __init__(
        self,
        *,
        consumer: KafkaConsumer,
        handler: RefreshCommandWorkerHandler,
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

    def run_until_idle(
        self,
        *,
        timeout_seconds: float = 1.0,
        max_empty_polls: int = 1,
    ) -> WorkerRunStats:
        polled = 0
        committed = 0
        empty_polls = 0

        while empty_polls < max_empty_polls:
            processed = self.run_once(timeout_seconds=timeout_seconds)
            if not processed:
                empty_polls += 1
                continue

            polled += 1
            committed += 1

        return WorkerRunStats(
            polled=polled,
            committed=committed,
            empty_polls=empty_polls,
        )

    def run_forever(self, *, timeout_seconds: float = 1.0) -> None:
        try:
            while True:
                self.run_once(timeout_seconds=timeout_seconds)
        finally:
            self._consumer.close()


def build_worker_dependencies(settings: DataUpdateSettings) -> RunnerDependencies:
    if settings.job_store == "memory":
        return RunnerDependencies.local_defaults(settings)

    if settings.job_store == "postgres":
        return RunnerDependencies.postgres_defaults(settings)

    raise ValueError(f"Unsupported DATA_UPDATE_JOB_STORE value: {settings.job_store!r}")


def build_kafka_worker(settings: DataUpdateSettings | None = None) -> RefreshWorker:
    resolved = settings or DataUpdateSettings.from_env()
    producer = ConfluentKafkaProducer(
        bootstrap_servers=resolved.kafka_bootstrap_servers,
    )
    consumer = ConfluentKafkaConsumer(
        bootstrap_servers=resolved.kafka_bootstrap_servers,
        group_id=resolved.kafka_consumer_group,
        topics=[resolved.kafka_command_topic],
    )

    event_publisher = WorkerEventPublisher(
        producer=producer,
        status_topic=resolved.kafka_status_topic,
        dlq_topic=resolved.kafka_dlq_topic,
        retry_5m_topic=resolved.kafka_retry_5m_topic,
        retry_1h_topic=resolved.kafka_retry_1h_topic,
    )

    dataset_event_publisher = KafkaDatasetEventPublisher(
        producer=producer,
        dataset_version_topic=resolved.kafka_dataset_version_topic,
        dataset_promotion_topic=resolved.kafka_dataset_promotion_topic,
    )

    dependencies = replace(
        build_worker_dependencies(resolved),
        dataset_event_publisher=dataset_event_publisher,
    )

    handler = RefreshCommandWorkerHandler(
        event_publisher=event_publisher,
        dependencies=dependencies,
    )
    return RefreshWorker(consumer=consumer, handler=handler)


def main() -> None:
    worker = build_kafka_worker()
    worker.run_forever()


if __name__ == "__main__":  # pragma: no cover - module entrypoint
    main()
