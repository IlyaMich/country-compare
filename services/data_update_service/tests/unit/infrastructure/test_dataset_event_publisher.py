from __future__ import annotations

from datetime import UTC, datetime

from data_update_service.infrastructure.dataset_event_publisher import (
    KafkaDatasetEventPublisher,
)
from data_update_service.infrastructure.kafka import InMemoryKafkaProducer
from data_update_service.orchestration.dataset_events import (
    DatasetPromotionEvent,
    DatasetVersionEvent,
)


def test_kafka_dataset_event_publisher_sends_version_and_promotion_events() -> None:
    producer = InMemoryKafkaProducer()
    publisher = KafkaDatasetEventPublisher(
        producer=producer,
        dataset_version_topic="country-compare.dataset.versions.v1",
        dataset_promotion_topic="country-compare.dataset.promotions.v1",
    )

    version_event = DatasetVersionEvent(
        event_id="evt_version",
        job_id="job_1",
        dataset_version="world_bank_v1",
        source_family="world_bank",
        artifact_uri="file:///tmp/world_bank_v1",
        parquet_sha256="a" * 64,
        manifest_sha256="b" * 64,
        catalog_sha256="c" * 64,
        validation_status="passed",
        row_count=1,
        country_count=1,
        metric_count=1,
        year_min=2020,
        year_max=2020,
        created_at=datetime.now(tz=UTC),
    )
    promotion_event = DatasetPromotionEvent(
        event_id="evt_promotion",
        dataset_version="world_bank_v1",
        channel="staging",
        previous_dataset_version=None,
        promoted_by="test",
        promoted_at=datetime.now(tz=UTC),
    )

    publisher.publish_dataset_version(version_event)
    publisher.publish_dataset_promotion(promotion_event)

    assert len(producer.messages) == 2

    assert producer.messages[0].topic == "country-compare.dataset.versions.v1"
    assert producer.messages[0].key == "world_bank_v1"
    assert producer.messages[0].headers["event_type"] == "DatasetVersionEvent"

    assert producer.messages[1].topic == "country-compare.dataset.promotions.v1"
    assert producer.messages[1].key == "staging"
    assert producer.messages[1].headers["event_type"] == "DatasetPromotionEvent"
