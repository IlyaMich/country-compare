from __future__ import annotations

from collections.abc import Mapping
from typing import Any

REDACTED = ""


_SENSITIVE_KEYS = {
    "api_key",
    "apikey",
    "authorization",
    "credentials",
    "messages",
    "password",
    "prompt",
    "raw_prompt",
    "raw_provider_response",
    "raw_request",
    "raw_response",
    "secret",
    "service_token",
    "system_prompt",
    "token",
    "user_prompt",
}


_SENSITIVE_KEY_PARTS = (
    "api_key",
    "apikey",
    "authorization",
    "bearer",
    "credential",
    "password",
    "raw_provider_response",
    "raw_request",
    "raw_response",
    "secret",
    "service_token",
    "token",
)


SAFE_METADATA_KEYS = frozenset(
    {
        "provider",
        "model",
        "prompt_version",
        "llm_calls",
        "input_tokens",
        "output_tokens",
        "latency_ms",
        "deployment_profile",
        "zdr_required",
        "zdr_confirmed",
        "max_horizon_years",
        "max_history_points",
        "max_input_chars",
        "max_output_tokens",
        "max_adjustment_pct",
        "structured_output",
        "bounded_adjustment",
        "queue_wait_ms",
        "max_concurrent_requests",
        "provider_latency_ms",
        "total_latency_ms",
        "retry_count",
    }
)


def is_sensitive_key(key: object) -> bool:
    """Return True when a key likely contains secret or raw payload data.

    This intentionally does not treat every key containing "prompt" as sensitive,
    because metadata such as "prompt_version" is safe and useful. Exact prompt
    payload keys such as "prompt", "raw_prompt", "system_prompt", and
    "user_prompt" are still redacted.
    """

    normalized = str(key).strip().lower()
    return normalized in _SENSITIVE_KEYS or any(
        part in normalized for part in _SENSITIVE_KEY_PARTS
    )


def redact_value(value: Any) -> Any:
    """Recursively redact sensitive mapping values."""

    if isinstance(value, Mapping):
        return {
            str(key): REDACTED if is_sensitive_key(key) else redact_value(nested)
            for key, nested in value.items()
        }

    if isinstance(value, list):
        return [redact_value(item) for item in value]

    if isinstance(value, tuple):
        return tuple(redact_value(item) for item in value)

    return value


def redact_mapping(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Return a copy of a mapping with sensitive values redacted."""

    return {
        str(key): REDACTED if is_sensitive_key(key) else redact_value(value)
        for key, value in payload.items()
    }


def safe_metadata(metadata: Mapping[str, Any] | None) -> dict[str, Any]:
    """Return only response-safe metadata.

    Uses an allowlist first, then applies redaction recursively to any allowed
    nested values. This keeps safe operational metadata such as provider, model,
    prompt_version, queue wait, latency, and retry count while excluding secrets,
    raw prompts, raw requests, raw provider responses, and unknown fields.
    """

    if not metadata:
        return {}

    safe: dict[str, Any] = {}
    for key, value in metadata.items():
        key_text = str(key)

        if key_text not in SAFE_METADATA_KEYS:
            continue

        if is_sensitive_key(key_text):
            continue

        safe[key_text] = redact_value(value)

    return safe


def debug_payload_logging_enabled(
    *,
    deployment_profile: str,
    debug_log_payloads: bool,
) -> bool:
    """Return whether debug payload logging may be enabled."""

    if deployment_profile == "public":
        return False

    return bool(debug_log_payloads)
