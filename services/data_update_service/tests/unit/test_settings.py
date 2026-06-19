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


def test_settings_reads_retry_topics(monkeypatch) -> None:
    monkeypatch.setenv("DATA_UPDATE_KAFKA_RETRY_5M_TOPIC", "retry.5m")
    monkeypatch.setenv("DATA_UPDATE_KAFKA_RETRY_1H_TOPIC", "retry.1h")

    settings = DataUpdateSettings.from_env()

    assert settings.kafka_retry_5m_topic == "retry.5m"
    assert settings.kafka_retry_1h_topic == "retry.1h"


def test_settings_reads_retry_relay_settings(monkeypatch) -> None:
    monkeypatch.setenv("DATA_UPDATE_KAFKA_RETRY_CONSUMER_GROUP", "retry-workers")
    monkeypatch.setenv("DATA_UPDATE_RETRY_5M_DELAY_SECONDS", "0")
    monkeypatch.setenv("DATA_UPDATE_RETRY_1H_DELAY_SECONDS", "10")

    settings = DataUpdateSettings.from_env()

    assert settings.kafka_retry_consumer_group == "retry-workers"
    assert settings.retry_5m_delay_seconds == 0
    assert settings.retry_1h_delay_seconds == 10


def test_settings_rejects_negative_retry_delay(monkeypatch) -> None:
    monkeypatch.setenv("DATA_UPDATE_RETRY_5M_DELAY_SECONDS", "-1")

    with pytest.raises(ValueError, match="DATA_UPDATE_RETRY_5M_DELAY_SECONDS"):
        DataUpdateSettings.from_env()


def test_settings_reads_dlq_consumer_group(monkeypatch) -> None:
    monkeypatch.setenv("DATA_UPDATE_KAFKA_DLQ_CONSUMER_GROUP", "dlq-inspectors")

    settings = DataUpdateSettings.from_env()

    assert settings.kafka_dlq_consumer_group == "dlq-inspectors"


def test_settings_reads_s3_artifact_store_env(monkeypatch) -> None:
    monkeypatch.setenv("DATA_UPDATE_ARTIFACT_STORE", "s3")
    monkeypatch.setenv("DATA_UPDATE_ARTIFACT_BUCKET", "country-compare-datasets")
    monkeypatch.setenv("DATA_UPDATE_ARTIFACT_PREFIX", "datasets")
    monkeypatch.setenv("DATA_UPDATE_ARTIFACT_ENDPOINT_URL", "http://localhost:9000")
    monkeypatch.setenv("DATA_UPDATE_ARTIFACT_REGION", "us-east-1")
    monkeypatch.setenv("DATA_UPDATE_ARTIFACT_ACCESS_KEY_ID", "minio")
    monkeypatch.setenv("DATA_UPDATE_ARTIFACT_SECRET_ACCESS_KEY", "minio123")

    settings = DataUpdateSettings.from_env()

    assert settings.artifact_store == "s3"
    assert settings.artifact_bucket == "country-compare-datasets"
    assert settings.artifact_prefix == "datasets"
    assert settings.artifact_endpoint_url == "http://localhost:9000"
    assert settings.artifact_region == "us-east-1"
    assert settings.artifact_access_key_id == "minio"
    assert settings.artifact_secret_access_key == "minio123"
