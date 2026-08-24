from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any

import pytest
import yaml

from tests.integration.data.fixture_rules import load_yaml_fixture

pytestmark = pytest.mark.integration

MANIFEST_PATH = Path("config/source_manifests/world_bank_real_data.yaml")
METRICS_CONFIG_PATH = Path("config/metrics.yaml")


def _load_yaml(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        payload = yaml.safe_load(handle)

    if not isinstance(payload, dict):
        raise AssertionError(f"{path} must contain a YAML mapping.")

    return payload


def test_every_world_bank_metric_has_an_approved_direction_review() -> None:
    review_fixture = load_yaml_fixture("metric_direction_reviews.yaml")
    directions = review_fixture.get("directions", {})

    assert isinstance(directions, dict)
    assert directions

    manifest = _load_yaml(MANIFEST_PATH)
    sources = manifest.get("sources", [])

    manifest_directions = {
        str(source["metric_id"]): bool(source["higher_is_better"]) for source in sources
    }

    assert set(directions) == set(manifest_directions)

    failures: list[dict[str, object]] = []

    for metric_id, expected_direction in manifest_directions.items():
        review = directions[metric_id]

        if review.get("review_status") != "approved":
            failures.append(
                {
                    "metric_id": metric_id,
                    "reason": "direction_not_approved",
                    "review_status": review.get("review_status"),
                }
            )

        reviewed_direction = review.get("higher_is_better")

        if reviewed_direction is not expected_direction:
            failures.append(
                {
                    "metric_id": metric_id,
                    "reason": "direction_mismatch",
                    "reviewed": reviewed_direction,
                    "manifest": expected_direction,
                }
            )

        rationale = str(review.get("rationale", "")).strip()

        if not rationale:
            failures.append(
                {
                    "metric_id": metric_id,
                    "reason": "missing_rationale",
                }
            )

    assert failures == []


def test_direction_reviews_match_metrics_config() -> None:
    review_fixture = load_yaml_fixture("metric_direction_reviews.yaml")
    directions = review_fixture["directions"]

    metrics_config = _load_yaml(METRICS_CONFIG_PATH)
    configured_metrics = metrics_config.get("metrics", {})

    assert set(directions) == set(configured_metrics)

    failures: list[dict[str, object]] = []

    for metric_id, review in directions.items():
        configured_direction = configured_metrics[metric_id]["higher_is_better"]

        if review["higher_is_better"] is not configured_direction:
            failures.append(
                {
                    "metric_id": metric_id,
                    "reason": "metrics_config_direction_mismatch",
                    "reviewed": review["higher_is_better"],
                    "configured": configured_direction,
                }
            )

    assert failures == []


def test_direction_review_date_is_valid() -> None:
    fixture = load_yaml_fixture("metric_direction_reviews.yaml")

    reviewed_at = fixture.get("reviewed_at")

    assert reviewed_at, "metric direction review must record reviewed_at"

    date.fromisoformat(str(reviewed_at))


def test_no_unresolved_direction_todos_remain() -> None:
    manifest_text = MANIFEST_PATH.read_text(encoding="utf-8")

    assert "TODO_REVIEW_DIRECTION" not in manifest_text
