from __future__ import annotations

import argparse
import json
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any


class SmokeFailure(RuntimeError):
    """Raised when the container smoke test fails."""


@dataclass(frozen=True)
class ApiResponse:
    status_code: int
    headers: dict[str, str]
    payload: dict[str, Any]


@dataclass(frozen=True)
class SmokeClient:
    base_url: str
    timeout_seconds: float

    def get(self, path: str, *, request_id: str | None = None) -> ApiResponse:
        return self.request("GET", path, request_id=request_id)

    def post(
        self,
        path: str,
        *,
        payload: dict[str, Any],
        request_id: str | None = None,
    ) -> ApiResponse:
        return self.request("POST", path, payload=payload, request_id=request_id)

    def request(
        self,
        method: str,
        path: str,
        *,
        payload: dict[str, Any] | None = None,
        request_id: str | None = None,
    ) -> ApiResponse:
        url = f"{self.base_url.rstrip('/')}{path}"
        body = None
        headers = {"Accept": "application/json"}

        if payload is not None:
            body = json.dumps(payload).encode("utf-8")
            headers["Content-Type"] = "application/json"

        if request_id:
            headers["X-Request-ID"] = request_id

        request = urllib.request.Request(
            url,
            data=body,
            headers=headers,
            method=method,
        )

        try:
            with urllib.request.urlopen(
                request,
                timeout=self.timeout_seconds,
            ) as response:
                response_body = response.read().decode("utf-8")
                return ApiResponse(
                    status_code=response.status,
                    headers=dict(response.headers.items()),
                    payload=_parse_json(response_body),
                )
        except urllib.error.HTTPError as exc:
            response_body = exc.read().decode("utf-8")
            raise SmokeFailure(
                f"{method} {path} returned HTTP {exc.code}: {response_body}"
            ) from exc


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Smoke test a running Country Compare API container."
    )
    parser.add_argument(
        "--base-url",
        default="http://127.0.0.1:8000",
        help="Base URL for the API container.",
    )
    parser.add_argument(
        "--timeout-seconds",
        type=float,
        default=5.0,
        help="Per-request timeout.",
    )
    parser.add_argument(
        "--wait-seconds",
        type=float,
        default=90.0,
        help="Maximum time to wait for /health and /ready.",
    )
    args = parser.parse_args()

    client = SmokeClient(
        base_url=args.base_url,
        timeout_seconds=args.timeout_seconds,
    )

    _wait_for_operational_endpoints(client, wait_seconds=args.wait_seconds)
    countries = _check_countries_metadata(client)
    metrics = _check_metrics_metadata(client)
    _check_dataset_metadata(client)
    _check_single_metric_comparison(client, countries=countries, metrics=metrics)

    print("API container smoke checks passed.")
    return 0


def _wait_for_operational_endpoints(
    client: SmokeClient,
    *,
    wait_seconds: float,
) -> None:
    deadline = time.time() + wait_seconds
    last_error: Exception | None = None

    while time.time() < deadline:
        try:
            health = client.get("/health", request_id="ci-smoke-health")
            if health.status_code != 200:
                raise SmokeFailure(f"/health returned {health.status_code}")

            ready = client.get("/ready", request_id="ci-smoke-ready")
            if ready.status_code != 200:
                raise SmokeFailure(f"/ready returned {ready.status_code}")

            _assert_request_id_header(health, expected="ci-smoke-health")
            _assert_request_id_header(ready, expected="ci-smoke-ready")
            return
        except (OSError, SmokeFailure, urllib.error.URLError) as exc:
            last_error = exc
            time.sleep(2)

    raise SmokeFailure(
        f"API did not become healthy/ready within {wait_seconds} seconds: "
        f"{last_error!r}"
    )


def _check_dataset_metadata(client: SmokeClient) -> None:
    response = client.get(
        "/api/v1/metadata/dataset",
        request_id="ci-smoke-dataset",
    )
    _assert_status(response, expected=200, label="/api/v1/metadata/dataset")
    _assert_request_id_header(response, expected="ci-smoke-dataset")

    payload = response.payload
    if payload.get("exists") is not True:
        raise SmokeFailure("Dataset metadata did not report exists=true.")

    row_count = payload.get("row_count")
    if not isinstance(row_count, int) or row_count <= 0:
        raise SmokeFailure(f"Dataset metadata has invalid row_count: {row_count!r}")


def _check_countries_metadata(client: SmokeClient) -> list[str]:
    response = client.get(
        "/api/v1/metadata/countries",
        request_id="ci-smoke-countries",
    )
    _assert_status(response, expected=200, label="/api/v1/metadata/countries")
    _assert_request_id_header(response, expected="ci-smoke-countries")

    countries_payload = response.payload.get("countries")
    if not isinstance(countries_payload, list) or not countries_payload:
        raise SmokeFailure("Countries metadata returned no countries.")

    country_codes = [
        str(item["code"])
        for item in countries_payload
        if isinstance(item, dict) and item.get("code")
    ]
    if len(country_codes) < 2:
        raise SmokeFailure(
            "Countries metadata must contain at least two countries for smoke comparison."
        )

    return country_codes


def _check_metrics_metadata(client: SmokeClient) -> list[str]:
    response = client.get(
        "/api/v1/metadata/metrics",
        request_id="ci-smoke-metrics",
    )
    _assert_status(response, expected=200, label="/api/v1/metadata/metrics")
    _assert_request_id_header(response, expected="ci-smoke-metrics")

    metrics_payload = response.payload.get("metrics")
    if not isinstance(metrics_payload, list) or not metrics_payload:
        raise SmokeFailure("Metrics metadata returned no metrics.")

    metric_ids = [
        str(item["metric_id"])
        for item in metrics_payload
        if isinstance(item, dict) and item.get("metric_id")
    ]
    if not metric_ids:
        raise SmokeFailure("Metrics metadata returned no metric_id values.")

    return metric_ids


def _check_single_metric_comparison(
    client: SmokeClient,
    *,
    countries: list[str],
    metrics: list[str],
) -> None:
    selected_countries = countries[: min(5, len(countries))]
    failures: list[str] = []

    for metric_id in metrics[: min(20, len(metrics))]:
        request_payload = {
            "country_codes": selected_countries,
            "metric_id": metric_id,
            "year_strategy": "latest_per_metric",
            "top_n": len(selected_countries),
        }

        try:
            response = client.post(
                "/api/v1/compare/single-metric",
                payload=request_payload,
                request_id="ci-smoke-comparison",
            )
            _assert_status(
                response,
                expected=200,
                label="/api/v1/compare/single-metric",
            )
            _assert_request_id_header(response, expected="ci-smoke-comparison")

            payload = response.payload
            if payload.get("ok") is not True:
                raise SmokeFailure(f"Comparison response ok was not true: {payload}")

            main_table = payload.get("tables", {}).get("main", {})
            row_count = main_table.get("row_count")
            if isinstance(row_count, int) and row_count > 0:
                print(
                    "Comparison smoke check used "
                    f"metric_id={metric_id!r}, country_codes={selected_countries!r}."
                )
                return

            failures.append(f"{metric_id}: empty comparison table")
        except (OSError, SmokeFailure, urllib.error.URLError) as exc:
            failures.append(f"{metric_id}: {exc!r}")

    raise SmokeFailure(
        "No candidate metric produced a non-empty single-metric comparison. "
        f"Failures: {failures}"
    )


def _assert_status(response: ApiResponse, *, expected: int, label: str) -> None:
    if response.status_code != expected:
        raise SmokeFailure(
            f"{label} returned {response.status_code}; expected {expected}. "
            f"Payload: {response.payload}"
        )


def _assert_request_id_header(response: ApiResponse, *, expected: str) -> None:
    actual = _get_header(response.headers, "X-Request-ID")
    if actual != expected:
        raise SmokeFailure(
            f"X-Request-ID mismatch. Expected {expected!r}, got {actual!r}."
        )


def _get_header(headers: dict[str, str], name: str) -> str | None:
    normalized = name.lower()
    for key, value in headers.items():
        if key.lower() == normalized:
            return value
    return None


def _parse_json(raw_body: str) -> dict[str, Any]:
    try:
        payload = json.loads(raw_body)
    except json.JSONDecodeError as exc:
        raise SmokeFailure(f"Response body was not valid JSON: {raw_body!r}") from exc

    if not isinstance(payload, dict):
        raise SmokeFailure(f"Response payload was not a JSON object: {payload!r}")

    return payload


if __name__ == "__main__":
    raise SystemExit(main())
