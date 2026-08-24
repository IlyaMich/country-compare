from __future__ import annotations

import csv
import math
from datetime import date
from pathlib import Path
from typing import Any

import pytest

from tests.integration.data.fixture_rules import load_yaml_fixture

pytestmark = pytest.mark.integration

ROOT = Path(__file__).resolve().parents[3]

SOURCE_REL_TOLERANCE = 1e-12
SOURCE_ABS_TOLERANCE = 1e-8


def _release_goldens() -> list[dict[str, Any]]:
    fixture = load_yaml_fixture("golden_values.yaml")
    release_dataset = fixture.get("release_dataset", {})

    if not isinstance(release_dataset, dict):
        raise AssertionError("golden_values.yaml release_dataset must be a mapping.")

    goldens = release_dataset.get("golden_values", [])

    if not isinstance(goldens, list) or not goldens:
        raise AssertionError(
            "golden_values.yaml release_dataset.golden_values "
            "must be a non-empty list."
        )

    return goldens


def _reviewed_mappings() -> dict[str, dict[str, Any]]:
    fixture = load_yaml_fixture("world_bank_metric_mappings.yaml")
    mappings = fixture.get("mappings", [])

    if not isinstance(mappings, list) or not mappings:
        raise AssertionError(
            "world_bank_metric_mappings.yaml mappings must be a non-empty list."
        )

    result: dict[str, dict[str, Any]] = {}

    for mapping in mappings:
        if not isinstance(mapping, dict):
            raise AssertionError("Every World Bank mapping must be a mapping.")

        metric_id = str(mapping["metric_id"])

        if metric_id in result:
            raise AssertionError(
                f"Duplicate World Bank mapping for metric_id={metric_id!r}."
            )

        result[metric_id] = mapping

    return result


def _snapshot_observation(
    *,
    mapping: dict[str, Any],
    country_code: str,
    year: int,
) -> tuple[float, str]:
    raw_path_value = mapping.get("raw_path")

    if not raw_path_value:
        raise AssertionError(
            f"Missing raw_path for metric_id={mapping.get('metric_id')!r}."
        )

    raw_path = ROOT / str(raw_path_value)

    if not raw_path.is_file():
        raise AssertionError(f"Raw World Bank snapshot does not exist: {raw_path}")

    with raw_path.open(
        "r",
        encoding="utf-8-sig",
        newline="",
    ) as handle:
        rows = list(csv.reader(handle))

    if len(rows) < 4:
        raise AssertionError(f"Unexpected World Bank CSV structure: {raw_path}")

    def _find_row(first_column: str) -> tuple[int, list[str]] | None:
        for index, row in enumerate(rows):
            if row and row[0] == first_column:
                return index, row

        return None

    data_source_match = _find_row("Data Source")

    if data_source_match is None:
        raise AssertionError(
            f"Missing Data Source row in World Bank snapshot: {raw_path}"
        )

    _, data_source_row = data_source_match

    if len(data_source_row) < 2 or data_source_row[1] != "World Development Indicators":
        raise AssertionError(
            f"Unexpected data source in {raw_path}: {data_source_row!r}"
        )

    last_updated_match = _find_row("Last Updated Date")

    if last_updated_match is None:
        raise AssertionError(
            f"Missing Last Updated Date in World Bank snapshot: {raw_path}"
        )

    _, last_updated_row = last_updated_match

    if len(last_updated_row) < 2 or not last_updated_row[1]:
        raise AssertionError(
            f"Invalid Last Updated Date row in World Bank snapshot: "
            f"{last_updated_row!r}"
        )

    snapshot_last_updated = last_updated_row[1]

    expected_snapshot_date = str(mapping.get("snapshot_last_updated", ""))

    if snapshot_last_updated != expected_snapshot_date:
        raise AssertionError(
            f"Snapshot date changed for metric_id={mapping['metric_id']!r}: "
            f"expected={expected_snapshot_date!r}, "
            f"actual={snapshot_last_updated!r}"
        )

    header_match = _find_row("Country Name")

    if header_match is None:
        raise AssertionError(f"Missing World Bank data header in snapshot: {raw_path}")

    header_index, header = header_match

    try:
        country_code_index = header.index("Country Code")
        indicator_code_index = header.index("Indicator Code")
        year_index = header.index(str(year))
    except ValueError as exc:
        raise AssertionError(
            f"Expected World Bank column missing from {raw_path}: {exc}"
        ) from exc

    expected_indicator_code = str(mapping["indicator_code"])

    matching_rows = [
        row
        for row in rows[header_index + 1 :]
        if len(row) > max(country_code_index, indicator_code_index, year_index)
        and row[country_code_index] == country_code
        and row[indicator_code_index] == expected_indicator_code
    ]

    if len(matching_rows) != 1:
        raise AssertionError(
            f"Expected exactly one raw observation for "
            f"{country_code}/{expected_indicator_code}/{year}; "
            f"found {len(matching_rows)}."
        )

    raw_value = matching_rows[0][year_index]

    if raw_value == "":
        raise AssertionError(
            f"Raw World Bank snapshot has no value for "
            f"{country_code}/{expected_indicator_code}/{year}."
        )

    return float(raw_value), snapshot_last_updated


def test_release_goldens_match_repository_world_bank_snapshots() -> None:
    goldens = _release_goldens()
    mappings = _reviewed_mappings()

    failures: list[dict[str, object]] = []

    for golden in goldens:
        country_code = str(golden["country_code"])
        metric_id = str(golden["metric_id"])
        year = int(golden["year"])
        expected_value = float(golden["expected_value"])

        mapping = mappings.get(metric_id)

        if mapping is None:
            failures.append(
                {
                    "country_code": country_code,
                    "metric_id": metric_id,
                    "year": year,
                    "reason": "missing_reviewed_mapping",
                }
            )
            continue

        expected_indicator_code = str(mapping["indicator_code"])
        golden_indicator_code = str(golden.get("indicator_code", ""))

        if golden_indicator_code != expected_indicator_code:
            failures.append(
                {
                    "country_code": country_code,
                    "metric_id": metric_id,
                    "year": year,
                    "reason": "indicator_code_mismatch",
                    "expected": expected_indicator_code,
                    "actual": golden_indicator_code,
                }
            )
            continue

        try:
            raw_value, snapshot_last_updated = _snapshot_observation(
                mapping=mapping,
                country_code=country_code,
                year=year,
            )
        except AssertionError as exc:
            failures.append(
                {
                    "country_code": country_code,
                    "metric_id": metric_id,
                    "year": year,
                    "reason": "snapshot_validation_failed",
                    "error": str(exc),
                }
            )
            continue

        if not math.isclose(
            raw_value,
            expected_value,
            rel_tol=SOURCE_REL_TOLERANCE,
            abs_tol=SOURCE_ABS_TOLERANCE,
        ):
            failures.append(
                {
                    "country_code": country_code,
                    "metric_id": metric_id,
                    "year": year,
                    "indicator_code": expected_indicator_code,
                    "reason": "golden_does_not_match_release_snapshot",
                    "golden_value": expected_value,
                    "snapshot_value": raw_value,
                    "snapshot_last_updated": snapshot_last_updated,
                }
            )

    assert failures == []


def test_release_goldens_are_marked_source_verified() -> None:
    goldens = _release_goldens()
    mappings = _reviewed_mappings()

    failures: list[dict[str, object]] = []

    for golden in goldens:
        country_code = str(golden["country_code"])
        metric_id = str(golden["metric_id"])
        year = int(golden["year"])

        if golden.get("review_status") != "verified":
            failures.append(
                {
                    "country_code": country_code,
                    "metric_id": metric_id,
                    "year": year,
                    "reason": "not_source_verified",
                    "review_status": golden.get("review_status"),
                }
            )

        verified_at_value = golden.get("verified_at")

        if not verified_at_value:
            failures.append(
                {
                    "country_code": country_code,
                    "metric_id": metric_id,
                    "year": year,
                    "reason": "missing_verified_at",
                }
            )
            continue

        try:
            verified_at = date.fromisoformat(str(verified_at_value))
        except ValueError:
            failures.append(
                {
                    "country_code": country_code,
                    "metric_id": metric_id,
                    "year": year,
                    "reason": "invalid_verified_at",
                    "verified_at": verified_at_value,
                }
            )
            continue

        mapping = mappings.get(metric_id)

        if mapping is None:
            continue

        snapshot_date_value = mapping.get("snapshot_last_updated")

        if not snapshot_date_value:
            failures.append(
                {
                    "country_code": country_code,
                    "metric_id": metric_id,
                    "year": year,
                    "reason": "missing_snapshot_last_updated",
                }
            )
            continue

        try:
            snapshot_date = date.fromisoformat(str(snapshot_date_value))
        except ValueError:
            failures.append(
                {
                    "country_code": country_code,
                    "metric_id": metric_id,
                    "year": year,
                    "reason": "invalid_snapshot_last_updated",
                    "snapshot_last_updated": snapshot_date_value,
                }
            )
            continue

        if verified_at < snapshot_date:
            failures.append(
                {
                    "country_code": country_code,
                    "metric_id": metric_id,
                    "year": year,
                    "reason": "verification_predates_snapshot",
                    "verified_at": str(verified_at),
                    "snapshot_last_updated": str(snapshot_date),
                }
            )

    assert failures == []
