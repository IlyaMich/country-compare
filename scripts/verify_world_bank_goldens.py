from __future__ import annotations

import json
import math
import sys
from pathlib import Path
from typing import Any
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import yaml

ROOT = Path(__file__).resolve().parents[1]
GOLDEN_PATH = ROOT / "tests" / "fixtures" / "data" / "golden_values.yaml"
MAPPINGS_PATH = ROOT / "tests" / "fixtures" / "data" / "world_bank_metric_mappings.yaml"
SOURCE_REL_TOLERANCE = 1e-12
SOURCE_ABS_TOLERANCE = 1e-8


def _load_yaml(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        payload = yaml.safe_load(handle)

    if not isinstance(payload, dict):
        raise RuntimeError(f"{path} must contain a YAML mapping.")

    return payload


def _allowed_delta(expected: float, golden: dict[str, Any]) -> float:
    tolerance_abs = float(golden.get("tolerance_abs") or 0.0)
    tolerance_pct = float(golden.get("tolerance_pct") or 0.0)

    return max(
        tolerance_abs,
        abs(expected) * tolerance_pct / 100.0,
    )


def _world_bank_value(
    *,
    country_code: str,
    indicator_code: str,
    year: int,
) -> float:
    query = urlencode(
        {
            "date": str(year),
            "format": "json",
            "per_page": "10",
        }
    )

    url = (
        "https://api.worldbank.org/v2/"
        f"country/{country_code}/indicator/{indicator_code}?{query}"
    )

    request = Request(
        url,
        headers={
            "User-Agent": "country-compare-data-verification/1.0",
        },
    )

    with urlopen(request, timeout=30) as response:
        payload = json.load(response)

    if not isinstance(payload, list) or len(payload) < 2:
        raise RuntimeError(
            f"Unexpected World Bank response for "
            f"{country_code}/{indicator_code}/{year}"
        )

    observations = payload[1]
    if not isinstance(observations, list) or not observations:
        raise RuntimeError(
            f"No World Bank observation for " f"{country_code}/{indicator_code}/{year}"
        )

    value = observations[0].get("value")
    if value is None:
        raise RuntimeError(
            f"World Bank returned null for " f"{country_code}/{indicator_code}/{year}"
        )

    return float(value)


def main() -> int:
    golden_fixture = _load_yaml(GOLDEN_PATH)
    mappings_fixture = _load_yaml(MAPPINGS_PATH)

    mappings = {
        str(item["metric_id"]): str(item["indicator_code"])
        for item in mappings_fixture["mappings"]
    }

    goldens = golden_fixture["release_dataset"]["golden_values"]

    failures: list[dict[str, object]] = []

    for golden in goldens:
        country_code = str(golden["country_code"])
        metric_id = str(golden["metric_id"])
        year = int(golden["year"])
        expected_value = float(golden["expected_value"])

        indicator_code = mappings.get(metric_id)
        if indicator_code is None:
            failures.append(
                {
                    "country_code": country_code,
                    "metric_id": metric_id,
                    "year": year,
                    "reason": "missing_indicator_mapping",
                }
            )
            continue

        golden_indicator_code = str(golden.get("indicator_code", ""))

        if golden_indicator_code != indicator_code:
            failures.append(
                {
                    "country_code": country_code,
                    "metric_id": metric_id,
                    "year": year,
                    "reason": "golden_indicator_mapping_mismatch",
                    "golden_indicator_code": golden_indicator_code,
                    "expected_indicator_code": indicator_code,
                }
            )
            continue

        try:
            actual_value = _world_bank_value(
                country_code=country_code,
                indicator_code=indicator_code,
                year=year,
            )
        except Exception as exc:
            failures.append(
                {
                    "country_code": country_code,
                    "metric_id": metric_id,
                    "year": year,
                    "indicator_code": indicator_code,
                    "reason": "world_bank_request_failed",
                    "error": str(exc),
                }
            )
            continue

        regression_allowed_delta = _allowed_delta(expected_value, golden)
        delta = abs(actual_value - expected_value)

        source_matches = math.isfinite(actual_value) and math.isclose(
            actual_value,
            expected_value,
            rel_tol=SOURCE_REL_TOLERANCE,
            abs_tol=SOURCE_ABS_TOLERANCE,
        )

        if source_matches:
            status = "PASS"
        elif delta <= regression_allowed_delta:
            status = "DRIFT"
        else:
            status = "FAIL"

        print(
            f"{status} "
            f"{country_code} {metric_id} {year} "
            f"[{indicator_code}] "
            f"fixture={expected_value!r} "
            f"world_bank={actual_value!r} "
            f"delta={delta!r} "
            f"regression_allowed={regression_allowed_delta!r}"
        )

        if not source_matches:
            failures.append(
                {
                    "country_code": country_code,
                    "metric_id": metric_id,
                    "year": year,
                    "indicator_code": indicator_code,
                    "expected_value": expected_value,
                    "world_bank_value": actual_value,
                    "actual_delta": delta,
                    "regression_allowed_delta": regression_allowed_delta,
                    "reason": (
                        "source_revision_within_regression_tolerance"
                        if status == "DRIFT"
                        else "source_revision_outside_regression_tolerance"
                    ),
                }
            )

    if failures:
        print("\nWorld Bank golden-value verification FAILED:")
        print(json.dumps(failures, indent=2))
        return 1

    print(
        f"\nWorld Bank golden-value verification passed "
        f"for {len(goldens)} observations."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
