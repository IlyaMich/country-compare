from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, cast

JobStoreBackend = Literal["memory", "postgres"]

DEFAULT_SOURCE_FAMILY = "world_bank"
DEFAULT_MANIFEST_PATH = Path("config/source_manifests/world_bank_real_data.yaml")
DEFAULT_ARTIFACT_ROOT = Path("data/artifacts/data_update")
DEFAULT_AUDIT_ROOT = Path("data/audit/data_update")
DEFAULT_WORKSPACE_ROOT = Path("data/work/data-update")
DEFAULT_MAX_ATTEMPTS = 3
DEFAULT_SOURCE_LOCK_TTL_SECONDS = 7200
DEFAULT_KAFKA_BOOTSTRAP_SERVERS = "localhost:9092"
DEFAULT_KAFKA_COMMAND_TOPIC = "country-compare.data-refresh.commands.v1"
DEFAULT_KAFKA_STATUS_TOPIC = "country-compare.data-refresh.status.v1"
DEFAULT_KAFKA_DLQ_TOPIC = "country-compare.data-refresh.dlq.v1"
DEFAULT_KAFKA_CONSUMER_GROUP = "data-update-workers"
DEFAULT_DATABASE_URL: str | None = None
DEFAULT_JOB_STORE: JobStoreBackend = "memory"
DEFAULT_POSTGRES_INITIALIZE_SCHEMA = False
DEFAULT_KAFKA_RETRY_5M_TOPIC = "country-compare.data-refresh.retry.5m.v1"
DEFAULT_KAFKA_RETRY_1H_TOPIC = "country-compare.data-refresh.retry.1h.v1"


@dataclass(frozen=True, slots=True)
class DataUpdateSettings:
    """Runtime settings used by the data update service."""

    default_source_family: str = DEFAULT_SOURCE_FAMILY
    default_manifest_path: Path = DEFAULT_MANIFEST_PATH
    artifact_root: Path = DEFAULT_ARTIFACT_ROOT
    audit_root: Path = DEFAULT_AUDIT_ROOT
    workspace_root: Path = DEFAULT_WORKSPACE_ROOT
    max_attempts: int = DEFAULT_MAX_ATTEMPTS
    source_lock_ttl_seconds: int = DEFAULT_SOURCE_LOCK_TTL_SECONDS

    kafka_bootstrap_servers: str = DEFAULT_KAFKA_BOOTSTRAP_SERVERS
    kafka_command_topic: str = DEFAULT_KAFKA_COMMAND_TOPIC
    kafka_status_topic: str = DEFAULT_KAFKA_STATUS_TOPIC
    kafka_dlq_topic: str = DEFAULT_KAFKA_DLQ_TOPIC
    kafka_consumer_group: str = DEFAULT_KAFKA_CONSUMER_GROUP
    kafka_retry_5m_topic: str = DEFAULT_KAFKA_RETRY_5M_TOPIC
    kafka_retry_1h_topic: str = DEFAULT_KAFKA_RETRY_1H_TOPIC

    database_url: str | None = DEFAULT_DATABASE_URL
    job_store: JobStoreBackend = DEFAULT_JOB_STORE
    postgres_initialize_schema: bool = DEFAULT_POSTGRES_INITIALIZE_SCHEMA

    @classmethod
    def from_env(cls) -> DataUpdateSettings:
        return cls(
            default_source_family=os.getenv(
                "DATA_UPDATE_DEFAULT_SOURCE_FAMILY",
                DEFAULT_SOURCE_FAMILY,
            ),
            default_manifest_path=Path(
                os.getenv(
                    "DATA_UPDATE_DEFAULT_MANIFEST",
                    str(DEFAULT_MANIFEST_PATH),
                )
            ),
            artifact_root=Path(
                os.getenv("DATA_UPDATE_ARTIFACT_ROOT", str(DEFAULT_ARTIFACT_ROOT))
            ),
            audit_root=Path(
                os.getenv("DATA_UPDATE_AUDIT_ROOT", str(DEFAULT_AUDIT_ROOT))
            ),
            workspace_root=Path(
                os.getenv("DATA_UPDATE_WORKSPACE_ROOT", str(DEFAULT_WORKSPACE_ROOT))
            ),
            max_attempts=_env_int("DATA_UPDATE_MAX_ATTEMPTS", DEFAULT_MAX_ATTEMPTS),
            source_lock_ttl_seconds=_env_int(
                "DATA_UPDATE_SOURCE_LOCK_TTL_SECONDS",
                DEFAULT_SOURCE_LOCK_TTL_SECONDS,
            ),
            kafka_bootstrap_servers=os.getenv(
                "DATA_UPDATE_KAFKA_BOOTSTRAP_SERVERS",
                DEFAULT_KAFKA_BOOTSTRAP_SERVERS,
            ),
            kafka_command_topic=os.getenv(
                "DATA_UPDATE_KAFKA_COMMAND_TOPIC",
                DEFAULT_KAFKA_COMMAND_TOPIC,
            ),
            kafka_status_topic=os.getenv(
                "DATA_UPDATE_KAFKA_STATUS_TOPIC",
                DEFAULT_KAFKA_STATUS_TOPIC,
            ),
            kafka_dlq_topic=os.getenv(
                "DATA_UPDATE_KAFKA_DLQ_TOPIC",
                DEFAULT_KAFKA_DLQ_TOPIC,
            ),
            kafka_consumer_group=os.getenv(
                "DATA_UPDATE_KAFKA_CONSUMER_GROUP",
                DEFAULT_KAFKA_CONSUMER_GROUP,
            ),
            kafka_retry_5m_topic=os.getenv(
                "DATA_UPDATE_KAFKA_RETRY_5M_TOPIC",
                DEFAULT_KAFKA_RETRY_5M_TOPIC,
            ),
            kafka_retry_1h_topic=os.getenv(
                "DATA_UPDATE_KAFKA_RETRY_1H_TOPIC",
                DEFAULT_KAFKA_RETRY_1H_TOPIC,
            ),
            database_url=_env_optional("DATA_UPDATE_DATABASE_URL"),
            job_store=_env_job_store("DATA_UPDATE_JOB_STORE", DEFAULT_JOB_STORE),
            postgres_initialize_schema=_env_bool(
                "DATA_UPDATE_POSTGRES_INITIALIZE_SCHEMA",
                DEFAULT_POSTGRES_INITIALIZE_SCHEMA,
            ),
        )


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default

    value = int(raw)
    if value <= 0:
        raise ValueError(f"{name} must be greater than zero")
    return value


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default

    normalized = raw.strip().lower()
    if normalized in {"1", "true", "yes", "y", "on"}:
        return True
    if normalized in {"0", "false", "no", "n", "off"}:
        return False

    raise ValueError(f"{name} must be a boolean value")


def _env_job_store(name: str, default: JobStoreBackend) -> JobStoreBackend:
    raw = _env_optional(name)
    if raw is None:
        return default

    normalized = raw.strip().lower()
    if normalized not in {"memory", "postgres"}:
        raise ValueError(f"{name} must be one of: memory, postgres")

    return cast(JobStoreBackend, normalized)


def _env_optional(name: str) -> str | None:
    raw = os.getenv(name)
    if raw is None:
        return None

    stripped = raw.strip()
    return stripped or None
