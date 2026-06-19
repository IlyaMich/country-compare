from __future__ import annotations

from data_update_service.infrastructure.kafka import KafkaProducer
from data_update_service.orchestration.dataset_events import (
    DatasetPromotionEvent,
    DatasetVersionEvent,
)


class KafkaDatasetEventPublisher:
    """Publishes dataset lifecycle events to Kafka."""

    def __init__(
        self,
        *,
        producer: KafkaProducer,
        dataset_version_topic: str,
        dataset_promotion_topic: str,
    ) -> None:
        self._producer = producer
        self._dataset_version_topic = dataset_version_topic
        self._dataset_promotion_topic = dataset_promotion_topic

    def publish_dataset_version(self, event: DatasetVersionEvent) -> None:
        self._producer.send(
            topic=self._dataset_version_topic,
            key=event.dataset_version,
            value=event.model_dump_json().encode("utf-8"),
            headers={
                "event_type": "DatasetVersionEvent",
                "schema_version": event.schema_version,
            },
        )
        self._producer.flush()

    def publish_dataset_promotion(self, event: DatasetPromotionEvent) -> None:
        self._producer.send(
            topic=self._dataset_promotion_topic,
            key=event.channel,
            value=event.model_dump_json().encode("utf-8"),
            headers={
                "event_type": "DatasetPromotionEvent",
                "schema_version": event.schema_version,
            },
        )
        self._producer.flush()
