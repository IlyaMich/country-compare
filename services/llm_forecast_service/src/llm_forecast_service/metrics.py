from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping
from dataclasses import dataclass, field
from threading import Lock
from typing import Final

DEFAULT_HTTP_DURATION_BUCKETS: Final = (
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
)
DEFAULT_FORECAST_DURATION_BUCKETS: Final = (
    0.05,
    0.1,
    0.25,
    0.5,
    1.0,
    2.5,
    5.0,
    10.0,
    30.0,
)
DEFAULT_PROVIDER_DURATION_BUCKETS: Final = (
    0.05,
    0.1,
    0.25,
    0.5,
    1.0,
    2.5,
    5.0,
    10.0,
    30.0,
)
DEFAULT_QUEUE_WAIT_BUCKETS: Final = (
    0.001,
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
)


LabelKey = tuple[tuple[str, str], ...]
CounterKey = tuple[str, LabelKey]
GaugeKey = tuple[str, LabelKey]
HistogramKey = tuple[str, LabelKey]


@dataclass(frozen=True)
class BucketConfig:
    http_duration_buckets: tuple[float, ...] = DEFAULT_HTTP_DURATION_BUCKETS
    forecast_duration_buckets: tuple[float, ...] = DEFAULT_FORECAST_DURATION_BUCKETS
    provider_duration_buckets: tuple[float, ...] = DEFAULT_PROVIDER_DURATION_BUCKETS
    queue_wait_buckets: tuple[float, ...] = DEFAULT_QUEUE_WAIT_BUCKETS


_BUCKET_CONFIG = BucketConfig()
_BUCKET_CONFIG_LOCK = Lock()


def configure_buckets(
    *,
    http_duration_buckets: tuple[float, ...] = DEFAULT_HTTP_DURATION_BUCKETS,
    forecast_duration_buckets: tuple[float, ...] = DEFAULT_FORECAST_DURATION_BUCKETS,
    provider_duration_buckets: tuple[float, ...] = DEFAULT_PROVIDER_DURATION_BUCKETS,
    queue_wait_buckets: tuple[float, ...] = DEFAULT_QUEUE_WAIT_BUCKETS,
) -> None:
    global _BUCKET_CONFIG

    _validate_bucket_values("http_duration_buckets", http_duration_buckets)
    _validate_bucket_values("forecast_duration_buckets", forecast_duration_buckets)
    _validate_bucket_values("provider_duration_buckets", provider_duration_buckets)
    _validate_bucket_values("queue_wait_buckets", queue_wait_buckets)

    with _BUCKET_CONFIG_LOCK:
        _BUCKET_CONFIG = BucketConfig(
            http_duration_buckets=http_duration_buckets,
            forecast_duration_buckets=forecast_duration_buckets,
            provider_duration_buckets=provider_duration_buckets,
            queue_wait_buckets=queue_wait_buckets,
        )


def _bucket_config() -> BucketConfig:
    with _BUCKET_CONFIG_LOCK:
        return _BUCKET_CONFIG


def _validate_bucket_values(name: str, values: tuple[float, ...]) -> None:
    if not values:
        raise ValueError(f"{name} must contain at least one bucket")

    previous: float | None = None
    for value in values:
        if value <= 0:
            raise ValueError(f"{name} bucket values must be greater than zero")
        if previous is not None and value <= previous:
            raise ValueError(f"{name} bucket values must be strictly increasing")
        previous = value


@dataclass
class HistogramState:
    buckets: tuple[float, ...]
    bucket_counts: dict[float, int] = field(default_factory=dict)
    count: int = 0
    total: float = 0.0

    def observe(self, value: float) -> None:
        self.count += 1
        self.total += value
        for bucket in self.buckets:
            if value <= bucket:
                self.bucket_counts[bucket] = self.bucket_counts.get(bucket, 0) + 1


class MetricsRegistry:
    def __init__(self) -> None:
        self._lock = Lock()
        self._counters: defaultdict[CounterKey, float] = defaultdict(float)
        self._gauges: dict[GaugeKey, float] = {}
        self._histograms: dict[HistogramKey, HistogramState] = {}

    def increment_counter(
        self,
        name: str,
        labels: Mapping[str, object] | None = None,
        amount: float = 1.0,
    ) -> None:
        with self._lock:
            self._counters[(name, _labels_key(labels))] += amount

    def set_gauge(
        self,
        name: str,
        value: float,
        labels: Mapping[str, object] | None = None,
    ) -> None:
        with self._lock:
            self._gauges[(name, _labels_key(labels))] = value

    def observe_histogram(
        self,
        name: str,
        value: float,
        buckets: tuple[float, ...],
        labels: Mapping[str, object] | None = None,
    ) -> None:
        key = (name, _labels_key(labels))
        with self._lock:
            state = self._histograms.get(key)
            if state is None or state.buckets != buckets:
                state = HistogramState(buckets=buckets)
                self._histograms[key] = state
            state.observe(value)

    def render(self) -> str:
        lines: list[str] = []

        with self._lock:
            counters = dict(self._counters)
            gauges = dict(self._gauges)
            histograms = {
                key: HistogramState(
                    buckets=value.buckets,
                    bucket_counts=dict(value.bucket_counts),
                    count=value.count,
                    total=value.total,
                )
                for key, value in self._histograms.items()
            }

        for (name, labels), value in sorted(counters.items()):
            lines.append(f"# TYPE {name} counter")
            lines.append(f"{name}{_format_labels(labels)} {_format_number(value)}")

        for (name, labels), value in sorted(gauges.items()):
            lines.append(f"# TYPE {name} gauge")
            lines.append(f"{name}{_format_labels(labels)} {_format_number(value)}")

        for (name, labels), state in sorted(histograms.items()):
            lines.append(f"# TYPE {name} histogram")
            for bucket in state.buckets:
                bucket_labels = dict(labels)
                bucket_labels["le"] = _format_number(bucket)
                lines.append(
                    f"{name}_bucket{_format_labels(_labels_key(bucket_labels))} "
                    f"{state.bucket_counts.get(bucket, 0)}"
                )

            inf_labels = dict(labels)
            inf_labels["le"] = "+Inf"
            lines.append(
                f"{name}_bucket{_format_labels(_labels_key(inf_labels))} {state.count}"
            )
            lines.append(f"{name}_count{_format_labels(labels)} {state.count}")
            lines.append(
                f"{name}_sum{_format_labels(labels)} {_format_number(state.total)}"
            )

        return "\n".join(lines) + "\n"


_REGISTRY = MetricsRegistry()


def record_http_request(
    *,
    method: str,
    path: str,
    status_code: int,
    duration_seconds: float,
) -> None:
    labels = {
        "method": method,
        "path": path,
        "status_code": str(status_code),
    }
    _REGISTRY.increment_counter("llm_http_requests_total", labels)
    _REGISTRY.observe_histogram(
        "llm_http_request_duration_seconds",
        duration_seconds,
        _bucket_config().http_duration_buckets,
        labels,
    )


def record_exception(*, exc_type: str) -> None:
    _REGISTRY.increment_counter("llm_http_exceptions_total", {"type": exc_type})


def record_auth_failure(*, reason: str) -> None:
    _REGISTRY.increment_counter("llm_auth_failures_total", {"reason": reason})


def record_forecast_request(
    *,
    status: str,
    provider: str,
    error_code: str | None,
    duration_seconds: float,
) -> None:
    labels = {
        "status": status,
        "provider": provider,
        "error_code": error_code or "",
    }
    _REGISTRY.increment_counter("llm_forecast_requests_total", labels)
    _REGISTRY.observe_histogram(
        "llm_forecast_duration_seconds",
        duration_seconds,
        _bucket_config().forecast_duration_buckets,
        {"provider": provider},
    )


def record_provider_duration(
    *,
    provider: str,
    model: str,
    duration_seconds: float,
) -> None:
    _REGISTRY.observe_histogram(
        "llm_provider_duration_seconds",
        duration_seconds,
        _bucket_config().provider_duration_buckets,
        {"provider": provider, "model": model},
    )


def record_provider_error(
    *,
    provider: str,
    error_code: str,
) -> None:
    _REGISTRY.increment_counter(
        "llm_provider_errors_total",
        {"provider": provider, "error_code": error_code},
    )


def observe_queue_wait(*, duration_seconds: float) -> None:
    _REGISTRY.observe_histogram(
        "llm_queue_wait_seconds",
        duration_seconds,
        _bucket_config().queue_wait_buckets,
    )


def record_queue_rejection() -> None:
    _REGISTRY.increment_counter("llm_queue_rejections_total")


def set_inflight_requests(value: int) -> None:
    _REGISTRY.set_gauge("llm_inflight_requests", float(value))


def record_validation_failure(*, code: str) -> None:
    _REGISTRY.increment_counter("llm_validation_failures_total", {"code": code})


def render_metrics() -> str:
    return _REGISTRY.render()


def reset_metrics_for_tests() -> None:
    global _REGISTRY
    _REGISTRY = MetricsRegistry()
    configure_buckets()


def _labels_key(labels: Mapping[str, object] | None) -> LabelKey:
    if not labels:
        return ()
    return tuple(sorted((str(key), str(value)) for key, value in labels.items()))


def _format_labels(labels: LabelKey) -> str:
    if not labels:
        return ""

    rendered = ",".join(
        f'{key}="{_escape_label_value(value)}"' for key, value in labels
    )
    return "{" + rendered + "}"


def _escape_label_value(value: str) -> str:
    return value.replace("\\", "\\\\").replace("\n", "\\n").replace('"', '\\"')


def _format_number(value: float) -> str:
    if value == float("inf"):
        return "+Inf"
    if value.is_integer():
        return str(int(value))
    return str(value)
