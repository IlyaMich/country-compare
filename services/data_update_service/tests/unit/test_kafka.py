from __future__ import annotations

from data_update_service.infrastructure.kafka import (
    InMemoryKafkaConsumer,
    InMemoryKafkaProducer,
    KafkaMessage,
)


def test_in_memory_producer_records_messages() -> None:
    producer = InMemoryKafkaProducer()

    producer.send(
        topic="status",
        key="job-1",
        value=b"{}",
        headers={"event_type": "test"},
    )

    assert len(producer.messages) == 1
    message = producer.messages[0]
    assert message.topic == "status"
    assert message.key == "job-1"
    assert message.value == b"{}"
    assert message.headers == {"event_type": "test"}


def test_in_memory_consumer_polls_and_commits_messages() -> None:
    message = KafkaMessage(topic="commands", key="world_bank", value=b"{}", offset=1)
    consumer = InMemoryKafkaConsumer([message])

    polled = consumer.poll()
    assert polled == message

    assert consumer.poll() is None
    consumer.commit(message)
    assert consumer.committed_messages == [message]
