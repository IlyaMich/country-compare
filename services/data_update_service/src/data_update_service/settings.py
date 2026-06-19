from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, cast

JobStoreBackend = Literal["memory", "postgres"]
ArtifactStoreBackend = Literal["filesystem", "s3"]

DEFAULT_SOURCE_FAMILY = "world_bank"
DEFAULT_MANIFEST_PATH = Path("config/source_manifests/world_bank_real_data.yaml")
DEFAULT_ARTIFACT_ROOT = Path("data/artifacts/data_update")
DEFAULT_ARTIFACT_STORE: ArtifactStoreBackend = "filesystem"
DEFAULT_ARTIFACT_BUCKET: str | None = None
DEFAULT_ARTIFACT_PREFIX = "datasets"
DEFAULT_ARTIFACT_ENDPOINT_URL: str | None = None
DEFAULT_ARTIFACT_REGION = "auto"
DEFAULT_ARTIFACT_ACCESS_KEY_ID: str | None = None
DEFAULT_ARTIFACT_SECRET_ACCESS_KEY: str | None = None
DEFAULT_AUDIT_ROOT = Path("data/audit/data_update")
DEFAULT_WORKSPACE_ROOT = Path("data/work/data-update")
DEFAULT_MAX_ATTEMPTS = 3
DEFAULT_SOURCE_LOCK_TTL_SECONDS = 7200
DEFAULT_KAFKA_BOOTSTRAP_SERVERS = "localhost:9092"
DEFAULT_KAFKA_COMMAND_TOPIC = "country-compare.data-refresh.commands.v1"
DEFAULT_KAFKA_STATUS_TOPIC = "country-compare.data-refresh.status.v1"
DEFAULT_KAFKA_DLQ_TOPIC = "country-compare.data-refresh.dlq.v1"
DEFAULT_KAFKA_CONSUMER_GROUP = "data-update-workers"
DEFAULT_KAFKA_RETRY_5M_TOPIC = "country-compare.data-refresh.retry.5m.v1"
DEFAULT_KAFKA_RETRY_1H_TOPIC = "country-compare.data-refresh.retry.1h.v1"
DEFAULT_KAFKA_RETRY_CONSUMER_GROUP = "data-update-retry-workers"
DEFAULT_KAFKA_DLQ_CONSUMER_GROUP = "data-update-dlq-inspector"
DEFAULT_KAFKA_DATASET_VERSION_TOPIC = "country-compare.dataset.versions.v1"
DEFAULT_KAFKA_DATASET_PROMOTION_TOPIC = "country-compare.dataset.promotions.v1"
DEFAULT_RETRY_5M_DELAY_SECONDS = 300
DEFAULT_RETRY_1H_DELAY_SECONDS = 3600
DEFAULT_DATABASE_URL: str | None = None
DEFAULT_JOB_STORE: JobStoreBackend = "memory"
DEFAULT_POSTGRES_INITIALIZE_SCHEMA = False


@dataclass(frozen=True, slots=True)
class DataUpdateSettings:
    """Runtime settings used by the data update service."""

    default_source_family: str = DEFAULT_SOURCE_FAMILY
    default_manifest_path: Path = DEFAULT_MANIFEST_PATH
    artifact_root: Path = DEFAULT_ARTIFACT_ROOT
    artifact_store: ArtifactStoreBackend = DEFAULT_ARTIFACT_STORE
    artifact_bucket: str | None = DEFAULT_ARTIFACT_BUCKET
    artifact_prefix: str = DEFAULT_ARTIFACT_PREFIX
    artifact_endpoint_url: str | None = DEFAULT_ARTIFACT_ENDPOINT_URL
    artifact_region: str = DEFAULT_ARTIFACT_REGION
    artifact_access_key_id: str | None = DEFAULT_ARTIFACT_ACCESS_KEY_ID
    artifact_secret_access_key: str | None = DEFAULT_ARTIFACT_SECRET_ACCESS_KEY
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
    kafka_retry_consumer_group: str = DEFAULT_KAFKA_RETRY_CONSUMER_GROUP
    kafka_dlq_consumer_group: str = DEFAULT_KAFKA_DLQ_CONSUMER_GROUP
    kafka_dataset_version_topic: str = DEFAULT_KAFKA_DATASET_VERSION_TOPIC
    kafka_dataset_promotion_topic: str = DEFAULT_KAFKA_DATASET_PROMOTION_TOPIC
    retry_5m_delay_seconds: int = DEFAULT_RETRY_5M_DELAY_SECONDS
    retry_1h_delay_seconds: int = DEFAULT_RETRY_1H_DELAY_SECONDS

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
            artifact_store=_env_artifact_store(
                "DATA_UPDATE_ARTIFACT_STORE",
                DEFAULT_ARTIFACT_STORE,
            ),
            artifact_bucket=_env_optional("DATA_UPDATE_ARTIFACT_BUCKET"),
            artifact_prefix=os.getenv(
                "DATA_UPDATE_ARTIFACT_PREFIX",
                DEFAULT_ARTIFACT_PREFIX,
            ).strip("/"),
            artifact_endpoint_url=_env_optional("DATA_UPDATE_ARTIFACT_ENDPOINT_URL"),
            artifact_region=os.getenv(
                "DATA_UPDATE_ARTIFACT_REGION",
                DEFAULT_ARTIFACT_REGION,
            ),
            artifact_access_key_id=_env_optional("DATA_UPDATE_ARTIFACT_ACCESS_KEY_ID"),
            artifact_secret_access_key=_env_optional(
                "DATA_UPDATE_ARTIFACT_SECRET_ACCESS_KEY"
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
            kafka_retry_consumer_group=os.getenv(
                "DATA_UPDATE_KAFKA_RETRY_CONSUMER_GROUP",
                DEFAULT_KAFKA_RETRY_CONSUMER_GROUP,
            ),
            kafka_dlq_consumer_group=os.getenv(
                "DATA_UPDATE_KAFKA_DLQ_CONSUMER_GROUP",
                DEFAULT_KAFKA_DLQ_CONSUMER_GROUP,
            ),
            kafka_dataset_version_topic=os.getenv(
                "DATA_UPDATE_KAFKA_DATASET_VERSION_TOPIC",
                DEFAULT_KAFKA_DATASET_VERSION_TOPIC,
            ),
            kafka_dataset_promotion_topic=os.getenv(
                "DATA_UPDATE_KAFKA_DATASET_PROMOTION_TOPIC",
                DEFAULT_KAFKA_DATASET_PROMOTION_TOPIC,
            ),
            retry_5m_delay_seconds=_env_non_negative_int(
                "DATA_UPDATE_RETRY_5M_DELAY_SECONDS",
                DEFAULT_RETRY_5M_DELAY_SECONDS,
            ),
            retry_1h_delay_seconds=_env_non_negative_int(
                "DATA_UPDATE_RETRY_1H_DELAY_SECONDS",
                DEFAULT_RETRY_1H_DELAY_SECONDS,
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


def _env_artifact_store(
    name: str,
    default: ArtifactStoreBackend,
) -> ArtifactStoreBackend:
    raw = _env_optional(name)

    if raw is None:
        return default

    normalized = raw.strip().lower()

    if normalized not in {"filesystem", "s3"}:
        raise ValueError(f"{name} must be one of: filesystem, s3")

    return cast(ArtifactStoreBackend, normalized)


def _env_optional(name: str) -> str | None:
    raw = os.getenv(name)
    if raw is None:
        return None

    stripped = raw.strip()
    return stripped or None


def _env_non_negative_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default

    value = int(raw)
    if value < 0:
        raise ValueError(f"{name} must be greater than or equal to zero")
    return value
