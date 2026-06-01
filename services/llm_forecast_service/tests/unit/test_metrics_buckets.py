from __future__ import annotations

import pytest

from llm_forecast_service import metrics
from llm_forecast_service.main import create_app
from llm_forecast_service.settings import ServiceSettings, SettingsError


@pytest.fixture(autouse=True)
def _reset_metrics() -> None:
    metrics.reset_metrics_for_tests()


def test_metric_buckets_parse_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLM_PROVIDER", "baseline_echo")
    monkeypatch.setenv("LLM_SERVICE_TOKEN", "test-token")
    monkeypatch.setenv("LLM_HTTP_DURATION_BUCKETS", "0.1, 0.5, 1.5")
    monkeypatch.setenv("LLM_FORECAST_DURATION_BUCKETS", "0.2,1,5")
    monkeypatch.setenv("LLM_PROVIDER_DURATION_BUCKETS", "0.3,2,6")
    monkeypatch.setenv("LLM_QUEUE_WAIT_BUCKETS", "0.01,0.1,1")

    settings = ServiceSettings.from_env()

    assert settings.http_duration_buckets == (0.1, 0.5, 1.5)
    assert settings.forecast_duration_buckets == (0.2, 1.0, 5.0)
    assert settings.provider_duration_buckets == (0.3, 2.0, 6.0)
    assert settings.queue_wait_buckets == (0.01, 0.1, 1.0)


def test_metric_buckets_reject_unsorted_values(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLM_PROVIDER", "baseline_echo")
    monkeypatch.setenv("LLM_SERVICE_TOKEN", "test-token")
    monkeypatch.setenv("LLM_HTTP_DURATION_BUCKETS", "0.5,0.1")

    with pytest.raises(SettingsError, match="strictly increasing"):
        ServiceSettings.from_env()


def test_create_app_configures_metric_buckets() -> None:
    settings = ServiceSettings(
        provider="baseline_echo",
        service_token="test-token",
        http_duration_buckets=(0.25, 0.75),
        forecast_duration_buckets=(0.5, 2.0),
        provider_duration_buckets=(0.6, 3.0),
        queue_wait_buckets=(0.01, 0.02),
    )

    app = create_app(settings=settings)
    assert app.state.settings.http_duration_buckets == (0.25, 0.75)

    metrics.record_http_request(
        method="GET",
        path="/health",
        status_code=200,
        duration_seconds=0.5,
    )
    rendered = metrics.render_metrics()

    assert (
        "llm_http_request_duration_seconds_bucket{"
        'le="0.25",method="GET",path="/health",status_code="200"}'
    ) in rendered
    assert (
        "llm_http_request_duration_seconds_bucket{"
        'le="0.75",method="GET",path="/health",status_code="200"}'
    ) in rendered
    assert (
        "llm_http_request_duration_seconds_bucket{"
        'le="1",method="GET",path="/health",status_code="200"}'
    ) not in rendered
