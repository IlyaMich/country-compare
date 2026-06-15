from __future__ import annotations

import pytest

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


def test_settings_reads_postgres_worker_env(monkeypatch) -> None:
    monkeypatch.setenv("DATA_UPDATE_JOB_STORE", "postgres")
    monkeypatch.setenv(
        "DATA_UPDATE_DATABASE_URL",
        "postgresql://country_compare:country_compare@localhost:5433/country_compare",
    )
    monkeypatch.setenv("DATA_UPDATE_POSTGRES_INITIALIZE_SCHEMA", "true")

    settings = DataUpdateSettings.from_env()

    assert settings.job_store == "postgres"
    assert (
        settings.database_url
        == "postgresql://country_compare:country_compare@localhost:5433/country_compare"
    )
    assert settings.postgres_initialize_schema is True


def test_settings_defaults_worker_store_to_memory(monkeypatch) -> None:
    monkeypatch.delenv("DATA_UPDATE_JOB_STORE", raising=False)
    monkeypatch.delenv("DATA_UPDATE_POSTGRES_INITIALIZE_SCHEMA", raising=False)

    settings = DataUpdateSettings.from_env()

    assert settings.job_store == "memory"
    assert settings.postgres_initialize_schema is False


def test_settings_rejects_invalid_job_store(monkeypatch) -> None:
    monkeypatch.setenv("DATA_UPDATE_JOB_STORE", "sqlite")

    with pytest.raises(ValueError, match="DATA_UPDATE_JOB_STORE"):
        DataUpdateSettings.from_env()


def test_settings_rejects_invalid_postgres_schema_flag(monkeypatch) -> None:
    monkeypatch.setenv("DATA_UPDATE_POSTGRES_INITIALIZE_SCHEMA", "maybe")

    with pytest.raises(ValueError, match="DATA_UPDATE_POSTGRES_INITIALIZE_SCHEMA"):
        DataUpdateSettings.from_env()
