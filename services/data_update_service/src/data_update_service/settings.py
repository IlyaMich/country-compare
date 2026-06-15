from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

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
        )


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    value = int(raw)
    if value <= 0:
        raise ValueError(f"{name} must be greater than zero")
    return value
