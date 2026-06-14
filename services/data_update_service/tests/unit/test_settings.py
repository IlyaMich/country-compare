from __future__ import annotations

from data_update_service.settings import DataUpdateSettings


def test_settings_reads_kafka_env(monkeypatch) -> None:
    monkeypatch.setenv("DATA_UPDATE_KAFKA_BOOTSTRAP_SERVERS", "kafka:9092")
    monkeypatch.setenv("DATA_UPDATE_KAFKA_COMMAND_TOPIC", "commands")
    monkeypatch.setenv("DATA_UPDATE_KAFKA_STATUS_TOPIC", "status")
    monkeypatch.setenv("DATA_UPDATE_KAFKA_DLQ_TOPIC", "dlq")
    monkeypatch.setenv("DATA_UPDATE_KAFKA_CONSUMER_GROUP", "workers")
    monkeypatch.setenv("DATA_UPDATE_SOURCE_LOCK_TTL_SECONDS", "60")

    settings = DataUpdateSettings.from_env()

    assert settings.kafka_bootstrap_servers == "kafka:9092"
    assert settings.kafka_command_topic == "commands"
    assert settings.kafka_status_topic == "status"
    assert settings.kafka_dlq_topic == "dlq"
    assert settings.kafka_consumer_group == "workers"
    assert settings.source_lock_ttl_seconds == 60
