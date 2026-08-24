from __future__ import annotations

import argparse
import json
import math
import urllib.error
import urllib.request
from numbers import Real
from pathlib import Path
from typing import Any

DEFAULT_FIXTURE_PATH = (
    Path(__file__).resolve().parents[1]
    / "tests"
    / "fixtures"
    / "validation"
    / "ops02_release_reference_v1.0.1.json"
)


def _request_json(
    *,
    base_url: str,
    path: str,
    api_key: str | None,
    timeout_seconds: float,
    method: str = "GET",
    payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    url = f"{base_url.rstrip('/')}{path}"

    headers = {
        "Accept": "application/json",
    }

    if api_key:
        headers["X-API-Key"] = api_key

    body: bytes | None = None

    if payload is not None:
        body = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"

    request = urllib.request.Request(
        url,
        data=body,
        headers=headers,
        method=method,
    )

    try:
        with urllib.request.urlopen(
            request,
            timeout=timeout_seconds,
        ) as response:
            raw_body = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        response_body = exc.read().decode(
            "utf-8",
            errors="replace",
        )
        raise RuntimeError(
            f"{method} {path} returned HTTP " f"{exc.code}: {response_body}"
        ) from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"{method} {path} failed: {exc}") from exc

    parsed = json.loads(raw_body)

    if not isinstance(parsed, dict):
        raise RuntimeError(f"{method} {path} did not return a JSON object.")

    return parsed


def _assert_expected_subset(
    *,
    expected: Any,
    actual: Any,
    path: str,
    relative_tolerance: float,
    absolute_tolerance: float,
) -> None:
    if isinstance(expected, dict):
        if not isinstance(actual, dict):
            raise AssertionError(
                f"{path}: expected object, " f"got {type(actual).__name__}"
            )

        for key, expected_value in expected.items():
            if key not in actual:
                raise AssertionError(f"{path}: missing expected key {key!r}")

            _assert_expected_subset(
                expected=expected_value,
                actual=actual[key],
                path=f"{path}.{key}",
                relative_tolerance=relative_tolerance,
                absolute_tolerance=absolute_tolerance,
            )

        return

    if isinstance(expected, list):
        if not isinstance(actual, list):
            raise AssertionError(
                f"{path}: expected list, " f"got {type(actual).__name__}"
            )

        if len(actual) != len(expected):
            raise AssertionError(
                f"{path}: expected {len(expected)} item(s), " f"got {len(actual)}"
            )

        for index, (expected_item, actual_item) in enumerate(
            zip(expected, actual, strict=True)
        ):
            _assert_expected_subset(
                expected=expected_item,
                actual=actual_item,
                path=f"{path}[{index}]",
                relative_tolerance=relative_tolerance,
                absolute_tolerance=absolute_tolerance,
            )

        return

    expected_is_number = isinstance(expected, Real) and not isinstance(expected, bool)
    actual_is_number = isinstance(actual, Real) and not isinstance(actual, bool)

    if expected_is_number and actual_is_number:
        if isinstance(expected, int) and isinstance(actual, int):
            if expected != actual:
                raise AssertionError(
                    f"{path}: expected {expected!r}, " f"got {actual!r}"
                )
            return

        if not math.isclose(
            float(expected),
            float(actual),
            rel_tol=relative_tolerance,
            abs_tol=absolute_tolerance,
        ):
            raise AssertionError(f"{path}: expected {expected!r}, " f"got {actual!r}")

        return

    if actual != expected:
        raise AssertionError(f"{path}: expected {expected!r}, " f"got {actual!r}")


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Validate a deployed Country Compare API against "
            "the frozen OPS-02 release reference pack."
        )
    )

    parser.add_argument(
        "--base-url",
        required=True,
    )
    parser.add_argument(
        "--api-key",
        default=None,
    )
    parser.add_argument(
        "--fixture",
        type=Path,
        default=DEFAULT_FIXTURE_PATH,
    )
    parser.add_argument(
        "--timeout-seconds",
        type=float,
        default=30.0,
    )

    args = parser.parse_args()

    fixture = json.loads(args.fixture.read_text(encoding="utf-8"))

    policy = fixture.get("comparison_policy", {})
    relative_tolerance = float(policy.get("relative_tolerance", 1e-12))
    absolute_tolerance = float(policy.get("absolute_tolerance", 1e-9))

    dataset_response = _request_json(
        base_url=args.base_url,
        path="/api/v1/metadata/dataset",
        api_key=args.api_key,
        timeout_seconds=args.timeout_seconds,
    )

    _assert_expected_subset(
        expected=fixture["dataset"],
        actual=dataset_response,
        path="dataset",
        relative_tolerance=relative_tolerance,
        absolute_tolerance=absolute_tolerance,
    )

    print(
        "OPS-02 dataset reference passed: " f"{fixture['dataset']['dataset_checksum']}"
    )

    cases = fixture.get("cases")

    if not isinstance(cases, list) or not cases:
        raise RuntimeError("OPS-02 fixture does not contain reference cases.")

    for case in cases:
        name = str(case["name"])
        method = str(case.get("method", "POST")).upper()
        path = str(case["path"])
        request_payload = case.get("request")

        if method != "POST":
            raise RuntimeError(f"{name}: unsupported method {method!r}")

        if not isinstance(request_payload, dict):
            raise RuntimeError(f"{name}: request must be a JSON object")

        response = _request_json(
            base_url=args.base_url,
            path=path,
            api_key=args.api_key,
            timeout_seconds=args.timeout_seconds,
            method=method,
            payload=request_payload,
        )

        _assert_expected_subset(
            expected=case["expected"],
            actual=response,
            path=name,
            relative_tolerance=relative_tolerance,
            absolute_tolerance=absolute_tolerance,
        )

        print(f"OPS-02 reference case passed: {name}")

    print(f"OPS-02 deployed API reference pack passed " f"({len(cases)} cases).")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
