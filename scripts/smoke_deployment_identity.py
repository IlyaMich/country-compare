from __future__ import annotations

import argparse
import json
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


def _parse_bool(value: str) -> bool:
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise argparse.ArgumentTypeError(
        f"Expected boolean value, got {value!r}."
    )


def _request_json(
    *,
    base_url: str,
    path: str,
    api_key: str | None = None,
    timeout_seconds: float = 30.0,
) -> tuple[int, dict[str, Any]]:
    url = f"{base_url.rstrip('/')}{path}"

    headers = {
        "Accept": "application/json",
    }

    if api_key:
        headers["X-API-Key"] = api_key

    request = Request(
        url,
        headers=headers,
        method="GET",
    )

    try:
        with urlopen(request, timeout=timeout_seconds) as response:
            status_code = response.status
            raw_body = response.read().decode("utf-8")
    except HTTPError as exc:
        status_code = exc.code
        raw_body = exc.read().decode("utf-8")
    except URLError as exc:
        raise RuntimeError(
            f"Request failed for {url}: {exc}"
        ) from exc

    if not raw_body:
        return status_code, {}

    try:
        parsed = json.loads(raw_body)
    except json.JSONDecodeError as exc:
        raise RuntimeError(
            f"GET {path} returned non-JSON content "
            f"with HTTP {status_code}."
        ) from exc

    if not isinstance(parsed, dict):
        raise RuntimeError(
            f"GET {path} did not return a JSON object."
        )

    return status_code, parsed


def _assert_equal(
    *,
    label: str,
    expected: Any,
    actual: Any,
) -> None:
    if actual != expected:
        raise AssertionError(
            f"{label}: expected {expected!r}, got {actual!r}"
        )


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Validate deployed Country Compare release identity "
            "and runtime configuration for OPS-04."
        )
    )

    parser.add_argument(
        "--api-base-url",
        required=True,
    )
    parser.add_argument(
        "--api-key",
        required=True,
    )
    parser.add_argument(
        "--expected-version",
        required=True,
    )
    parser.add_argument(
        "--expected-dataset-checksum",
        required=True,
    )
    parser.add_argument(
        "--expect-api-key-required",
        type=_parse_bool,
        default=True,
    )
    parser.add_argument(
        "--expect-llm-enabled",
        type=_parse_bool,
        required=True,
    )
    parser.add_argument(
        "--expect-docs-enabled",
        type=_parse_bool,
        required=True,
    )
    parser.add_argument(
        "--timeout-seconds",
        type=float,
        default=30.0,
    )

    args = parser.parse_args()

    #
    # 1. Release/application version
    #
    health_status, health = _request_json(
        base_url=args.api_base_url,
        path="/health",
        timeout_seconds=args.timeout_seconds,
    )

    _assert_equal(
        label="health HTTP status",
        expected=200,
        actual=health_status,
    )
    _assert_equal(
        label="health status",
        expected="ok",
        actual=health.get("status"),
    )
    _assert_equal(
        label="application version",
        expected=args.expected_version,
        actual=health.get("version"),
    )
    _assert_equal(
        label="API version",
        expected=args.expected_version,
        actual=health.get("api_version"),
    )

    print(
        "OPS-04 release version passed: "
        f"{args.expected_version}"
    )

    #
    # 2. API-key behavior
    #
    unauthenticated_status, _ = _request_json(
        base_url=args.api_base_url,
        path="/api/v1/metadata/dataset",
        timeout_seconds=args.timeout_seconds,
    )

    if args.expect_api_key_required:
        _assert_equal(
            label="unauthenticated metadata status",
            expected=401,
            actual=unauthenticated_status,
        )

        invalid_status, _ = _request_json(
            base_url=args.api_base_url,
            path="/api/v1/metadata/dataset",
            api_key="ops04-intentionally-invalid-key",
            timeout_seconds=args.timeout_seconds,
        )

        _assert_equal(
            label="invalid-key metadata status",
            expected=401,
            actual=invalid_status,
        )
    else:
        _assert_equal(
            label="unauthenticated metadata status",
            expected=200,
            actual=unauthenticated_status,
        )

    print(
        "OPS-04 API authentication behavior passed: "
        f"required={args.expect_api_key_required}"
    )

    #
    # 3. Readiness and dataset identity
    #
    ready_status, ready = _request_json(
        base_url=args.api_base_url,
        path="/ready",
        api_key=args.api_key,
        timeout_seconds=args.timeout_seconds,
    )

    _assert_equal(
        label="ready HTTP status",
        expected=200,
        actual=ready_status,
    )
    _assert_equal(
        label="ready status",
        expected="ready",
        actual=ready.get("status"),
    )

    ready_dataset = ready.get("dataset")
    if not isinstance(ready_dataset, dict):
        raise AssertionError(
            "/ready response does not contain dataset metadata."
        )

    _assert_equal(
        label="ready dataset checksum",
        expected=args.expected_dataset_checksum,
        actual=ready_dataset.get("dataset_checksum"),
    )

    ready_config = ready.get("config")
    if not isinstance(ready_config, dict):
        raise AssertionError(
            "/ready response does not contain config status."
        )

    _assert_equal(
        label="ready config valid",
        expected=True,
        actual=ready_config.get("valid"),
    )

    _assert_equal(
        label="ready config validated_against_dataset",
        expected=True,
        actual=ready_config.get("validated_against_dataset"),
    )

    print(
        "OPS-04 readiness identity passed: "
        f"{args.expected_dataset_checksum}"
    )

    #
    # 4. Metadata endpoint must report the same release dataset
    #
    metadata_status, metadata = _request_json(
        base_url=args.api_base_url,
        path="/api/v1/metadata/dataset",
        api_key=args.api_key,
        timeout_seconds=args.timeout_seconds,
    )

    _assert_equal(
        label="dataset metadata HTTP status",
        expected=200,
        actual=metadata_status,
    )
    _assert_equal(
        label="dataset exists",
        expected=True,
        actual=metadata.get("exists"),
    )
    _assert_equal(
        label="dataset schema valid",
        expected=True,
        actual=metadata.get("schema_valid"),
    )
    _assert_equal(
        label="dataset checksum",
        expected=args.expected_dataset_checksum,
        actual=metadata.get("dataset_checksum"),
    )

    print(
        "OPS-04 dataset metadata identity passed."
    )

    #
    # 5. LLM feature flag.
    #
    # A 503 is acceptable here if the feature is enabled but its
    # private service is not ready. OPS-05 validates connectivity.
    #
    llm_status, llm_ready = _request_json(
        base_url=args.api_base_url,
        path="/ready/llm",
        api_key=args.api_key,
        timeout_seconds=args.timeout_seconds,
    )

    if llm_status not in {200, 503}:
        raise AssertionError(
            f"/ready/llm returned unexpected HTTP status {llm_status}."
        )

    _assert_equal(
        label="LLM enabled flag",
        expected=args.expect_llm_enabled,
        actual=llm_ready.get("enabled"),
    )

    print(
        "OPS-04 LLM feature flag passed: "
        f"enabled={args.expect_llm_enabled}"
    )

    #
    # 6. API docs feature flag
    #
    docs_status, _ = _request_json(
        base_url=args.api_base_url,
        path="/openapi.json",
        api_key=args.api_key,
        timeout_seconds=args.timeout_seconds,
    )

    if args.expect_docs_enabled:
        _assert_equal(
            label="OpenAPI docs status",
            expected=200,
            actual=docs_status,
        )
    else:
        _assert_equal(
            label="OpenAPI docs status",
            expected=404,
            actual=docs_status,
        )

    print(
        "OPS-04 API docs feature flag passed: "
        f"enabled={args.expect_docs_enabled}"
    )

    print("OPS-04 deployed release identity checks passed.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())