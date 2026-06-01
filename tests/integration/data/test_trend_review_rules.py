from __future__ import annotations

from pathlib import Path

import pytest
import yaml

pytestmark = pytest.mark.integration

TREND_RULES_PATH = (
    Path(__file__).resolve().parents[2]
    / "fixtures"
    / "data"
    / "trend_review_rules.yaml"
)


def test_reviewed_trend_anomalies_have_release_quality_reasons() -> None:
    content = yaml.safe_load(TREND_RULES_PATH.read_text(encoding="utf-8")) or {}
    reviewed_anomalies = content.get("reviewed_anomalies") or []

    bad_entries = []

    for entry in reviewed_anomalies:
        reason = str(entry.get("reason", "")).strip()
        if not reason or "TODO" in reason.upper():
            bad_entries.append(entry)

    assert not bad_entries, bad_entries[:25]
