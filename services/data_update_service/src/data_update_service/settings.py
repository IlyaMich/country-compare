from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class DataUpdateSettings:
    """Runtime settings used by the Milestone 1 CLI runner."""

    default_source_family: str = "world_bank"
    default_manifest_path: Path = Path(
        "config/source_manifests/world_bank_real_data.yaml"
    )
    artifact_root: Path = Path("data/artifacts/data_update")
    audit_root: Path = Path("data/audit/data_update")
    max_attempts: int = 3
    source_lock_ttl_seconds: int = 7200
