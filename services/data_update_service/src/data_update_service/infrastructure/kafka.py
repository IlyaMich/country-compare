from __future__ import annotations

from collections import deque
from collections.abc import Iterable, Mapping, MutableSequence
from dataclasses import dataclass, field
from threading import RLock
from typing import Any, Protocol, cast


class KafkaProducer(Protocol):
    def send(
        self,
        *,
        topic: str,
        key: str | None,
        value: bytes,
        headers: Mapping[str, str] | None = None,
    ) -> None:
        """Publish a Kafka message."""

    def flush(self) -> None:
        """Flush buffered producer messages, if the implementation buffers."""


class KafkaConsumer(Protocol):
    def poll(self, timeout_seconds: float = 1.0) -> KafkaMessage | None:
        """Return the next message, or None when no message is available."""

    def commit(self, message: KafkaMessage) -> None:
        """Commit a processed message offset."""

    def close(self) -> None:
        """Close the consumer."""


@dataclass(frozen=True, slots=True)
class KafkaMessage:
    topic: str
    key: str | None
    value: bytes
    headers: Mapping[str, str] = field(default_factory=dict)
    partition: int | None = None
    offset: int | None = None
    native_message: Any | None = field(default=None, repr=False, compare=False)


@dataclass(frozen=True, slots=True)
class PublishedKafkaMessage:
    topic: str
    key: str | None
    value: bytes
    headers: Mapping[str, str] = field(default_factory=dict)


class InMemoryKafkaProducer:
    """Deterministic producer fake used by unit tests and local adapter tests."""

    def __init__(
        self, messages: MutableSequence[PublishedKafkaMessage] | None = None
    ) -> None:
        self._lock = RLock()
        self.messages: MutableSequence[PublishedKafkaMessage] = (
            messages if messages is not None else []
        )

    def send(
        self,
        *,
        topic: str,
        key: str | None,
        value: bytes,
        headers: Mapping[str, str] | None = None,
    ) -> None:
        with self._lock:
            self.messages.append(
                PublishedKafkaMessage(
                    topic=topic,
                    key=key,
                    value=value,
                    headers=dict(headers or {}),
                )
            )

    def flush(self) -> None:
        return None


class InMemoryKafkaConsumer:
    """Deterministic consumer fake with explicit commit tracking."""

    def __init__(self, messages: Iterable[KafkaMessage] = ()) -> None:
        self._messages = deque(messages)
        self.committed_messages: list[KafkaMessage] = []
        self.closed = False

    def poll(self, timeout_seconds: float = 1.0) -> KafkaMessage | None:
        del timeout_seconds
        if self.closed or not self._messages:
            return None
        return self._messages.popleft()

    def commit(self, message: KafkaMessage) -> None:
        if self.closed:
            raise RuntimeError("cannot commit with a closed consumer")
        self.committed_messages.append(message)

    def close(self) -> None:
        self.closed = True


class KafkaDependencyMissingError(RuntimeError):
    """Raised when the optional Kafka runtime dependency is not installed."""


class KafkaConsumerError(RuntimeError):
    """Raised when the broker consumer reports an error."""


def _decode_header_value(value: str | bytes | None) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8")
    return value


def _normalize_headers(raw_headers: object) -> dict[str, str]:
    if raw_headers is None:
        return {}

    items: Iterable[tuple[str, str | bytes | None]]

    if isinstance(raw_headers, Mapping):
        items = cast(Iterable[tuple[str, str | bytes | None]], raw_headers.items())
    else:
        items = cast(Iterable[tuple[str, str | bytes | None]], raw_headers)

    return {str(key): _decode_header_value(value) for key, value in items}


class ConfluentKafkaProducer:
    """Small adapter around confluent-kafka for production Kafka publishing.

    The dependency is optional so unit tests and the CLI path do not require a
    broker client. Install the service with the `kafka` extra before using this
    adapter in a worker container.
    """

    def __init__(self, *, bootstrap_servers: str) -> None:
        try:
            from confluent_kafka import Producer
        except ImportError as exc:  # pragma: no cover - depends on optional package
            raise KafkaDependencyMissingError(
                "confluent-kafka is required for the Kafka worker runtime; "
                "install services/data_update_service[kafka]."
            ) from exc

        self._producer = Producer({"bootstrap.servers": bootstrap_servers})

    def send(
        self,
        *,
        topic: str,
        key: str | None,
        value: bytes,
        headers: Mapping[str, str] | None = None,
    ) -> None:
        self._producer.produce(
            topic,
            key=key.encode("utf-8") if key is not None else None,
            value=value,
            headers=list((headers or {}).items()),
        )
        self._producer.poll(0)

    def flush(self) -> None:
        self._producer.flush()


class ConfluentKafkaConsumer:
    """Small adapter around confluent-kafka for command topic consumption."""

    def __init__(
        self,
        *,
        bootstrap_servers: str,
        group_id: str,
        topics: list[str],
        auto_offset_reset: str = "earliest",
    ) -> None:
        try:
            from confluent_kafka import Consumer
        except ImportError as exc:  # pragma: no cover - depends on optional package
            raise KafkaDependencyMissingError(
                "confluent-kafka is required for the Kafka worker runtime; "
                "install services/data_update_service[kafka]."
            ) from exc

        self._consumer = Consumer(
            {
                "bootstrap.servers": bootstrap_servers,
                "group.id": group_id,
                "enable.auto.commit": False,
                "auto.offset.reset": auto_offset_reset,
            }
        )
        self._consumer.subscribe(topics)

    def poll(self, timeout_seconds: float = 1.0) -> KafkaMessage | None:
        message = self._consumer.poll(timeout_seconds)
        if message is None:
            return None
        error = message.error()
        if error is not None:
            raise KafkaConsumerError(str(error))
        key_bytes = message.key()
        key = key_bytes.decode("utf-8") if isinstance(key_bytes, bytes) else key_bytes
        return KafkaMessage(
            topic=str(message.topic()),
            key=key,
            value=bytes(message.value() or b""),
            headers=_normalize_headers(message.headers()),
            partition=message.partition(),
            offset=message.offset(),
            native_message=message,
        )

    def commit(self, message: KafkaMessage) -> None:
        if message.native_message is None:
            raise ValueError("cannot commit a KafkaMessage without native_message")
        self._consumer.commit(message=message.native_message, asynchronous=False)

    def close(self) -> None:
        self._consumer.close()
