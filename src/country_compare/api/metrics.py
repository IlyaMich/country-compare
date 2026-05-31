from __future__ import annotations

import math
import threading
import time
from collections import defaultdict
from collections.abc import Iterable

from fastapi import Request, status
from fastapi.responses import PlainTextResponse, Response

_BUCKETS: tuple[float, ...] = (
    0.005,
    0.01,
    0.025,
    0.05,
    0.1,
    0.25,
    0.5,
    1.0,
    2.5,
    5.0,
    10.0,
    math.inf,
)


def normalize_route_path(request: Request) -> str:
    """Return a stable low-cardinality route label for metrics."""

    route = request.scope.get("route")
    path = getattr(route, "path", None)
    if isinstance(path, str) and path:
        return path
    return request.url.path or "unknown"


class MetricsRegistry:
    """Small in-process Prometheus text exporter.

    This intentionally avoids an extra dependency. It is process-local, so multi-worker
    deployments should scrape every worker or replace this with prometheus-client's
    multiprocess mode later.
    """

    def __init__(self, buckets: Iterable[float] = _BUCKETS) -> None:
        self._buckets = tuple(buckets)
        self._lock = threading.Lock()
        self._requests: defaultdict[tuple[str, str, str], int] = defaultdict(int)
        self._duration_buckets: defaultdict[tuple[str, str, str, float], int] = (
            defaultdict(int)
        )
        self._duration_sum: defaultdict[tuple[str, str, str], float] = defaultdict(
            float
        )
        self._duration_count: defaultdict[tuple[str, str, str], int] = defaultdict(int)
        self._exceptions: defaultdict[tuple[str, str, str], int] = defaultdict(int)
        self._auth_failures: defaultdict[str, int] = defaultdict(int)
        self._created_at = time.time()

    def record_request(
        self,
        *,
        method: str,
        path: str,
        status_code: int,
        duration_seconds: float,
    ) -> None:
        normalized_method = method.upper()
        normalized_status = str(status_code)
        key = (normalized_method, path, normalized_status)
        with self._lock:
            self._requests[key] += 1
            self._duration_sum[key] += duration_seconds
            self._duration_count[key] += 1
            for bucket in self._buckets:
                if duration_seconds <= bucket:
                    self._duration_buckets[(*key, bucket)] += 1

    def record_exception(
        self,
        *,
        exception_type: str,
        status_code: int,
        error_code: str | None,
    ) -> None:
        with self._lock:
            self._exceptions[
                (exception_type, str(status_code), error_code or "unknown")
            ] += 1

    def record_auth_failure(self, *, reason: str) -> None:
        with self._lock:
            self._auth_failures[reason] += 1

    def render_prometheus(self) -> str:
        with self._lock:
            requests = dict(self._requests)
            duration_buckets = dict(self._duration_buckets)
            duration_sum = dict(self._duration_sum)
            duration_count = dict(self._duration_count)
            exceptions = dict(self._exceptions)
            auth_failures = dict(self._auth_failures)
            created_at = self._created_at

        build_labels = _labels(created_at=f"{created_at:.0f}")
        lines: list[str] = [
            "# HELP country_compare_api_build_info Static API process information.",
            "# TYPE country_compare_api_build_info gauge",
            f"country_compare_api_build_info{build_labels} 1",
            "# HELP country_compare_api_requests_total Total HTTP requests.",
            "# TYPE country_compare_api_requests_total counter",
        ]
        for (method, path, status_value), count in sorted(requests.items()):
            request_labels = _labels(
                method=method,
                path=path,
                status=status_value,
            )
            lines.append(f"country_compare_api_requests_total{request_labels} {count}")

        lines.extend(
            [
                "# HELP country_compare_api_request_duration_seconds HTTP request duration.",
                "# TYPE country_compare_api_request_duration_seconds histogram",
            ]
        )
        for (method, path, status_value), count in sorted(duration_count.items()):
            for bucket in self._buckets:
                bucket_count = duration_buckets.get(
                    (method, path, status_value, bucket), 0
                )
                le = "+Inf" if math.isinf(bucket) else _format_bucket(bucket)
                bucket_labels = _labels(
                    method=method,
                    path=path,
                    status=status_value,
                    le=le,
                )
                lines.append(
                    "country_compare_api_request_duration_seconds_bucket"
                    f"{bucket_labels} {bucket_count}"
                )

            duration_labels = _labels(
                method=method,
                path=path,
                status=status_value,
            )
            lines.append(
                "country_compare_api_request_duration_seconds_sum"
                f"{duration_labels} {duration_sum[(method, path, status_value)]:.9f}"
            )
            lines.append(
                "country_compare_api_request_duration_seconds_count"
                f"{duration_labels} {count}"
            )

        lines.extend(
            [
                "# HELP country_compare_api_exceptions_total Total API error responses.",
                "# TYPE country_compare_api_exceptions_total counter",
            ]
        )
        for (exception_type, status_value, error_code), count in sorted(
            exceptions.items()
        ):
            exception_labels = _labels(
                exception_type=exception_type,
                status=status_value,
                error_code=error_code,
            )
            lines.append(
                "country_compare_api_exceptions_total" f"{exception_labels} {count}"
            )

        lines.extend(
            [
                "# HELP country_compare_api_auth_failures_total Authentication failures by reason.",
                "# TYPE country_compare_api_auth_failures_total counter",
            ]
        )
        for reason, count in sorted(auth_failures.items()):
            auth_labels = _labels(reason=reason)
            lines.append(
                f"country_compare_api_auth_failures_total{auth_labels} {count}"
            )

        return "\n".join(lines) + "\n"

    def reset(self) -> None:
        with self._lock:
            self._requests.clear()
            self._duration_buckets.clear()
            self._duration_sum.clear()
            self._duration_count.clear()
            self._exceptions.clear()
            self._auth_failures.clear()
            self._created_at = time.time()


metrics_registry = MetricsRegistry()


async def metrics_response(request: Request) -> Response:
    api_settings = getattr(request.app.state, "api_settings", None)
    if not getattr(api_settings, "enable_metrics", False):
        return PlainTextResponse(
            "metrics disabled\n", status_code=status.HTTP_404_NOT_FOUND
        )
    return PlainTextResponse(
        metrics_registry.render_prometheus(),
        media_type="text/plain; version=0.0.4; charset=utf-8",
    )


def _labels(**values: str) -> str:
    body = ",".join(f'{name}="{_escape(value)}"' for name, value in values.items())
    return f"{{{body}}}"


def _escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace("\n", "\\n").replace('"', '\\"')


def _format_bucket(bucket: float) -> str:
    return f"{bucket:g}"
