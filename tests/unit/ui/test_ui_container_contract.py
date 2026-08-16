from __future__ import annotations

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[3]


def test_ui_dockerfile_does_not_embed_dataset() -> None:
    dockerfile = (ROOT / "Dockerfile.ui").read_text(encoding="utf-8")

    assert "COPY data /app/data" not in dockerfile


def test_default_compose_does_not_mount_dataset_into_ui() -> None:
    compose_path = ROOT / "docker-compose.yml"

    with compose_path.open("r", encoding="utf-8") as handle:
        compose = yaml.safe_load(handle)

    ui_service = compose["services"]["ui"]
    volumes = ui_service.get("volumes", [])

    assert not any(_volume_targets_path(volume, "/app/data") for volume in volumes)


def _volume_targets_path(volume: object, target: str) -> bool:
    if isinstance(volume, str):
        parts = volume.split(":")
        return len(parts) >= 2 and parts[1] == target

    if isinstance(volume, dict):
        return volume.get("target") == target

    return False
