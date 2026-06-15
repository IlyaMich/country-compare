from __future__ import annotations

from pathlib import Path

from data_update_service.orchestration.commands import RefreshCommand
from data_update_service.settings import DataUpdateSettings


def test_refresh_command_serializes_acquisition_mode() -> None:
    command = RefreshCommand.create(
        source_family="World_Bank",
        manifest_path=Path("config/source_manifests/world_bank_real_data.yaml"),
        acquisition_mode="auto",
    )

    assert command.source_family == "world_bank"
    assert command.acquisition_mode == "auto"
    assert "world_bank:full_refresh:auto:" in command.idempotency_key
    assert command.model_dump(mode="json")["acquisition_mode"] == "auto"


def test_settings_reads_workspace_root_from_env(monkeypatch) -> None:
    monkeypatch.setenv("DATA_UPDATE_WORKSPACE_ROOT", "custom/workspace")

    settings = DataUpdateSettings.from_env()

    assert settings.workspace_root == Path("custom/workspace")
