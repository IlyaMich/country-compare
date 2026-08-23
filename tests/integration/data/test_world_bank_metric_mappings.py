from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any

import pytest
import yaml

from tests.integration.data.fixture_rules import load_yaml_fixture

pytestmark = pytest.mark.integration

MANIFEST_PATH = Path("config/source_manifests/world_bank_real_data.yaml")


def _load_world_bank_manifest() -> dict[str, Any]:
    with MANIFEST_PATH.open("r", encoding="utf-8") as handle:
        payload = yaml.safe_load(handle)

    if not isinstance(payload, dict):
        raise AssertionError("World Bank source manifest must be a mapping.")

    return payload


def test_reviewed_world_bank_mappings_match_source_manifest() -> None:
    fixture = load_yaml_fixture("world_bank_metric_mappings.yaml")
    mappings = fixture.get("mappings", [])

    assert isinstance(mappings, list)
    assert mappings, "Authoritative World Bank mapping fixture must not be empty."

    manifest = _load_world_bank_manifest()
    sources = manifest.get("sources", [])

    assert isinstance(sources, list)
    assert sources, "World Bank source manifest must contain sources."

    fixture_by_metric: dict[str, dict[str, Any]] = {}
    for mapping in mappings:
        assert isinstance(mapping, dict)

        metric_id = str(mapping["metric_id"])
        assert (
            metric_id not in fixture_by_metric
        ), f"Duplicate authoritative mapping for metric_id={metric_id!r}"

        fixture_by_metric[metric_id] = mapping

    manifest_by_metric: dict[str, dict[str, Any]] = {}
    for source in sources:
        assert isinstance(source, dict)

        metric_id = str(source["metric_id"])
        assert (
            metric_id not in manifest_by_metric
        ), f"Duplicate World Bank manifest source for metric_id={metric_id!r}"

        manifest_by_metric[metric_id] = source

    assert set(fixture_by_metric) == set(manifest_by_metric), (
        "Authoritative World Bank mapping fixture must cover exactly the "
        "metrics present in the production World Bank source manifest."
    )

    failures: list[dict[str, object]] = []

    for metric_id, expected in fixture_by_metric.items():
        actual = manifest_by_metric[metric_id]

        expected_code = str(expected["indicator_code"])
        actual_code = str(actual["expected_indicator_code"])

        if actual_code != expected_code:
            failures.append(
                {
                    "metric_id": metric_id,
                    "reason": "indicator_code_mismatch",
                    "expected": expected_code,
                    "actual": actual_code,
                }
            )

    assert failures == []


def test_authoritative_world_bank_mappings_are_source_verified() -> None:
    fixture = load_yaml_fixture("world_bank_metric_mappings.yaml")
    mappings = fixture.get("mappings", [])

    failures: list[dict[str, object]] = []

    for mapping in mappings:
        metric_id = str(mapping["metric_id"])
        indicator_code = str(mapping.get("indicator_code", ""))

        if mapping.get("review_status") != "verified":
            failures.append(
                {
                    "metric_id": metric_id,
                    "reason": "not_verified",
                    "review_status": mapping.get("review_status"),
                }
            )

        verified_at = mapping.get("verified_at")
        if not verified_at:
            failures.append(
                {
                    "metric_id": metric_id,
                    "reason": "missing_verified_at",
                }
            )
        else:
            try:
                date.fromisoformat(str(verified_at))
            except ValueError:
                failures.append(
                    {
                        "metric_id": metric_id,
                        "reason": "invalid_verified_at",
                        "value": verified_at,
                    }
                )

        source_url = str(mapping.get("source_url", ""))
        if not source_url.startswith("https://data.worldbank.org/indicator/"):
            failures.append(
                {
                    "metric_id": metric_id,
                    "reason": "invalid_source_url",
                    "value": source_url,
                }
            )

        if indicator_code and indicator_code not in source_url:
            failures.append(
                {
                    "metric_id": metric_id,
                    "reason": "indicator_code_not_in_source_url",
                    "indicator_code": indicator_code,
                    "source_url": source_url,
                }
            )

    assert failures == []
