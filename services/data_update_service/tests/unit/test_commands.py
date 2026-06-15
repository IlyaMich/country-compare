from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest
from pydantic import ValidationError

from data_update_service.orchestration.commands import RefreshCommand


def test_refresh_command_create_sets_ids_and_defaults() -> None:
    command = RefreshCommand.create(
        source_family="World_Bank",
        manifest_path="config/source_manifests/world_bank_real_data.yaml",
        requested_at=datetime(2026, 6, 13, tzinfo=UTC),
    )

    assert command.schema_version == "1.0"
    assert command.command_type == "refresh_source"
    assert command.source_family == "world_bank"
    assert command.command_id.startswith("cmd_20260613T000000Z_")
    assert command.job_id.startswith("job_20260613T000000Z_world_bank_")
    assert command.idempotency_key.startswith("world_bank:full_refresh:2026-06-13:")
    assert command.attempt == 1
    assert command.max_attempts == 3


def test_refresh_command_requires_promotion_channel_when_promoting() -> None:
    with pytest.raises(ValidationError, match="promotion_channel is required"):
        RefreshCommand.create(
            source_family="world_bank",
            manifest_path="manifest.yaml",
            promote=True,
            promotion_channel=None,
        )


def test_refresh_command_rejects_attempt_above_max_attempts() -> None:
    with pytest.raises(ValidationError, match="attempt must be less than or equal"):
        RefreshCommand.create(
            source_family="world_bank",
            manifest_path="manifest.yaml",
            attempt=4,
            max_attempts=3,
        )


def test_refresh_command_normalizes_windows_manifest_path_for_transport() -> None:
    command = RefreshCommand.create(
        source_family="world_bank",
        manifest_path=r"config\source_manifests\world_bank_real_data.yaml",
        requested_at=datetime(2026, 6, 13, tzinfo=UTC),
    )

    assert command.manifest_path == "config/source_manifests/world_bank_real_data.yaml"
    assert command.manifest == Path("config/source_manifests/world_bank_real_data.yaml")
