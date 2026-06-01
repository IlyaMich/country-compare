from __future__ import annotations

from llm_forecast_service.privacy import safe_metadata


def test_safe_metadata_preserves_latency_and_queue_fields() -> None:
    metadata = safe_metadata(
        {
            "provider": "mistral",
            "model": "mistral-large-latest",
            "queue_wait_ms": 12,
            "provider_latency_ms": 34,
            "total_latency_ms": 46,
            "max_concurrent_requests": 1,
            "authorization": "Bearer secret",
            "raw_provider_response": "secret",
        }
    )

    assert metadata == {
        "provider": "mistral",
        "model": "mistral-large-latest",
        "queue_wait_ms": 12,
        "provider_latency_ms": 34,
        "total_latency_ms": 46,
        "max_concurrent_requests": 1,
    }
